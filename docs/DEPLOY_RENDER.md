# Deploy Running Plan Bot to Render.com

Same pattern as [jira-daily-report](https://github.com/Hazanel/jira-daily-report): **GitHub repo + Render web service**.

Telegram sends HTTP webhooks to Render (like Slack slash commands), so the free tier can sleep and wake on use.

---

## Why Render (not GitHub Actions)?

| | GitHub Actions | Render web service |
|--|----------------|-------------------|
| jira daily report | ✅ cron once/day | slash server always reachable |
| this bot | ❌ can't listen for Telegram | ✅ webhook wakes on photo |

GitHub stores the code; Render runs it.

---

## Step 1: Create the Telegram bot

1. Telegram → **@BotFather** → `/newbot`
2. Copy the token

## Step 2: Push this repo to GitHub

```bash
cd running-plan-bot
git init
git add .
git commit -m "Initial running plan Telegram bot"
gh repo create running-plan-bot --public --source=. --remote=origin --push
```

## Step 3: Deploy on Render

### Option A: Blueprint (easiest)

1. https://dashboard.render.com/select-repo  
2. Select **`Hazanel/running-plan-bot`** (or your fork)  
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
| `INTERVALS_ATHLETE_ID` | e.g. `i800203` |
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
export INTERVALS_ATHLETE_ID=i800203
python3 bot_server.py   # polling mode when PUBLIC_URL unset
```
