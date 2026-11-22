import io
import os
import re
import sys
import json
import base64
import requests
from PIL import Image

# ==============================================================================
# Configuration (secrets from env)
# ==============================================================================
INTERVALS_ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID", "")
INTERVALS_API_KEY = os.environ.get("INTERVALS_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

RUNNER_NAME = os.environ.get("RUNNER_NAME", "runner")
DEFAULT_IMAGE = "running_plan.jpg"
YEAR = int(os.environ.get("PLAN_YEAR", "2026"))
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
INTERVALS_URL = f"https://intervals.icu/api/v1/athlete/{INTERVALS_ATHLETE_ID}/events"
# ==============================================================================


def _require_secrets() -> None:
    missing = [k for k, v in (
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("INTERVALS_API_KEY", INTERVALS_API_KEY),
        ("INTERVALS_ATHLETE_ID", INTERVALS_ATHLETE_ID),
    ) if not v]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")


def image_to_base64(image_path: str) -> str:
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((1280, 1280))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def clean_distances(text: str) -> str:
    def repl(match):
        num = float(match.group(1))
        return f"{num:g}km"
    return re.sub(r'(\d+(?:\.\d+)?)\s*km\b', repl, text, flags=re.IGNORECASE)


def parse_handwritten_plan(image_path: str) -> list[dict]:
    _require_secrets()
    b64_image = image_to_base64(image_path)

    prompt = f"""
    You are an expert running coach parsing a handwritten weekly running plan written in Hebrew for the runner: "{RUNNER_NAME}".
    The year is {YEAR}.
    Output all workout names and descriptions strictly in English. This plan is strictly outdoor road/track running (Run only).

    Carefully read the entire attached sheet (including brackets, side notes, and arrows) and convert the workouts into the exact Intervals.icu structured workout format.

    Critical parsing rules:
    1. Runner filtering for "{RUNNER_NAME}": If there are split instructions or specific notes for names, extract ONLY the version applicable to "{RUNNER_NAME}".
    2. Brackets and repeated blocks: Only the lines enclosed inside the bracket are repeated! Steps before/after the bracket happen ONLY ONCE.
    3. EXPAND ALL REPEATED SETS EXPLICITLY: NEVER write standalone loop headers like `- 2x`. Write out every set step-by-step.
    4. Strides (מתגברות): expand as alternating `0.1km` fast and `0.1km Z1` recovery lines.
    5. Progressive side notes with arrows: write out each set with calculated paces.
    6. Ignore circled total mileage numbers on the side.
    7. Every description line MUST start with `- ` then distance in `km` and pace/zone.
       - Pace: `- 3km 5:30/km pace`
       - Easy: `- 8km Z2`

    Return ONLY valid JSON matching this exact structure (no markdown backticks):
    {{
      "workouts": [
        {{
          "date": "YYYY-MM-DD",
          "name": "Workout title in English",
          "description": "- step 1\\n- step 2"
        }}
      ]
    }}
    """

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}},
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    print(f"Sending image to {MODEL_NAME}...")
    last_err = None
    for attempt in range(1, 4):
        try:
            res = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(10, 180))
            res.raise_for_status()
            resp_json = res.json()
            break
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            print(f"Attempt {attempt}/3 timed out or failed ({e}); retrying...")
    else:
        raise last_err

    first_candidate = next(iter(resp_json.get("candidates", [])), {})
    parts = first_candidate.get("content", {}).get("parts", [])
    first_part = next(iter(parts), {})
    text = first_part.get("text", "{}").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    data = json.loads(text)
    if isinstance(data, list):
        workouts = data
    elif isinstance(data, dict):
        workouts = data.get("workouts", [])
    else:
        raise ValueError(f"Unexpected Gemini JSON type: {type(data).__name__}")

    if not isinstance(workouts, list):
        raise ValueError(f"'workouts' must be a list, got {type(workouts).__name__}")

    for w in workouts:
        if isinstance(w, dict):
            w["description"] = clean_distances(w.get("description", ""))
    print(f"Parsed {len(workouts)} workout(s).")
    return workouts


def delete_existing_workouts(workouts: list[dict]):
    if not workouts:
        return
    auth = ("API_KEY", INTERVALS_API_KEY)
    dates = sorted(w["date"] for w in workouts)
    oldest = next(iter(dates), "")
    newest = dates[-1] if dates else ""

    print(f"Checking existing planned workouts between {oldest} and {newest}...")
    res = requests.get(
        INTERVALS_URL,
        params={"oldest": oldest, "newest": newest},
        auth=auth,
        timeout=15,
    )
    if res.status_code != 200:
        print(f"[WARN] Could not fetch existing events: {res.status_code}")
        return

    target_dates = set(dates)
    for event in res.json():
        event_date = event.get("start_date_local", "")[:10]
        if event.get("category") == "WORKOUT" and event_date in target_dates:
            event_id = event["id"]
            del_res = requests.delete(f"{INTERVALS_URL}/{event_id}", auth=auth, timeout=15)
            if del_res.status_code in (200, 204):
                print(f"[DELETED] Old workout on {event_date}: {event.get('name')}")
            else:
                print(f"[WARN] Failed to delete {event_id}: {del_res.status_code}")


def upload_to_intervals(workouts: list[dict]):
    _require_secrets()
    delete_existing_workouts(workouts)
    auth = ("API_KEY", INTERVALS_API_KEY)

    for w in workouts:
        payload = {
            "category": "WORKOUT",
            "start_date_local": f"{w['date']}T07:00:00",
            "type": "Run",
            "name": w["name"],
            "description": w["description"],
        }
        res = requests.post(INTERVALS_URL, json=payload, auth=auth, timeout=15)
        if res.status_code in (200, 201):
            print(f"[OK] Uploaded: {w['date']} | {w['name']}")
        else:
            print(f"[ERROR] Failed {w['date']}: {res.status_code} - {res.text}")


if __name__ == "__main__":
    args = sys.argv[1:]
    img_file = next(iter(args), DEFAULT_IMAGE)

    print(f"Analyzing '{img_file}' for {RUNNER_NAME}...")
    workouts = parse_handwritten_plan(img_file)

    print("\n--- Parsed Workouts Preview ---")
    for w in workouts:
        print(f"\nDate: {w['date']} | {w['name']}")
        print(w["description"])

    confirm = input("\nDelete old workouts in these dates & upload new ones? (y/n): ")
    if confirm.strip().lower() == "y":
        upload_to_intervals(workouts)
        print("\nDone! Workouts will sync to your Suunto app shortly.")
    else:
        print("Upload canceled.")
