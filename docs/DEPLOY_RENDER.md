# Deploy Running Plan Bot to Render.com

**GitHub** holds the code. **Render** runs a Docker web service that receives Telegram webhooks.

---

## Why Render (not GitHub Actions)?

GitHub Actions is fine for a once-a-day cron job. This bot must answer when you send a photo, so it needs a reachable HTTP server. Render free web service sleeps when idle and wakes on the next request.

---

## Step 1: Create the Telegram bot

1. Telegram → **@BotFather** → `/newbot`
2. Copy the token

## Step 2: Repo on GitHub

Already at `https://github.com/Hazanel/running-plan-bot` (push updates with `git push`).

## Step 3: Deploy on Render

### Option A: Blueprint (easiest)

1. https://dashboard.render.com/select-repo  
2. Select **`Hazanel/running-plan-bot`**  
3. Render reads `render.yaml` → **Apply**

### Option B: Manual

1. **New → Web Service** → connect the GitHub repo  
2. Runtime: **Docker**, instance: **Free**  
3. Health check path: `/health`

## Step 4: Environment variables

In the Render service → **Environment**:

| Key | Value |
|-----|--------|
| `TELEGRAM_BOT_TOKEN` | from BotFather |
| `GEMINI_API_KEY` | Google AI Studio key |
| `INTERVALS_API_KEY` | intervals.icu API key |
| `INTERVALS_ATHLETE_ID` | your intervals.icu athlete id |
| `RUNNER_NAME` | name shown in Telegram replies |
| `PORT` | `8080` (already in render.yaml) |

`RENDER_EXTERNAL_URL` is set by Render automatically — the bot uses it to register the Telegram webhook.

Save → wait for deploy (~2–3 min).

## Step 5: Use from your phone

1. Open your bot in Telegram → `/start`  
2. WhatsApp plan photo → **Share → Telegram → bot**  
3. First message after idle may take ~30s (Render cold start)

## Local test (no Render)

```bash
export TELEGRAM_BOT_TOKEN=...
export GEMINI_API_KEY=...
export INTERVALS_API_KEY=...
export INTERVALS_ATHLETE_ID=your_athlete_id
export RUNNER_NAME="Your Name"
python3 bot_server.py   # polling mode when PUBLIC_URL unset
```
