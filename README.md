# Running Plan Bot

WhatsApp plan photo → Telegram → Gemini parse → Intervals.icu / Suunto.

Same hosting pattern as [jira-daily-report](https://github.com/Hazanel/jira-daily-report):

- **GitHub** — source of truth  
- **Render.com** — free web service (webhook + `/health`)  
- **Secrets** — set in Render dashboard (never commit keys)

## Phone flow

1. WhatsApp → open plan image → **Share → Telegram → this bot**  
2. Bot replies with parsed workouts and uploads them  

## Deploy

See **[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)**.

## Local

```bash
export TELEGRAM_BOT_TOKEN=...
export GEMINI_API_KEY=...
export INTERVALS_API_KEY=...
export INTERVALS_ATHLETE_ID=i800203
pip install -r requirements.txt
python3 bot_server.py
```
