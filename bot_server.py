#!/usr/bin/env python3
"""
Telegram bot + HTTP health endpoint for Render.

Local (no PUBLIC_URL): long-polling getUpdates.
Render (RENDER_EXTERNAL_URL set): webhook — Telegram POSTs to /telegram.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from suunto_uploader import RUNNER_NAME, parse_handwritten_plan, upload_to_intervals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("running-plan-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
PORT = int(os.environ.get("PORT", "8080"))
# Render sets RENDER_EXTERNAL_URL like https://running-plan-bot.onrender.com
PUBLIC_URL = (
    os.environ.get("PUBLIC_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or ""
).rstrip("/")

# Deduplicate Telegram retries of the same update (slow Gemini/upload used to
# delay the webhook 200, so Telegram POSTed again and we uploaded twice).
_seen_update_ids: set[int] = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Send me a photo of the handwritten plan for {RUNNER_NAME}.\n"
        "I'll parse it and upload to Intervals.icu (Suunto).\n\n"
        "From WhatsApp: open image → Share → Telegram → this bot."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.photo:
        return

    await msg.reply_text("Got it — parsing the plan…")
    photo = msg.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)

    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "plan.jpg"
        await tg_file.download_to_drive(custom_path=str(img_path))

        try:
            workouts = await asyncio.to_thread(parse_handwritten_plan, str(img_path))
        except Exception as e:
            log.exception("parse failed")
            await msg.reply_text(f"Parse failed: {e}")
            return

        if not workouts:
            await msg.reply_text("No workouts found in the image.")
            return

        preview = [f"Parsed {len(workouts)} workout(s):"]
        for w in workouts:
            preview.append(f"• {w.get('date')} — {w.get('name')}")
        await msg.reply_text("\n".join(preview))
        await msg.reply_text("Uploading to Intervals.icu…")

        try:
            await asyncio.to_thread(upload_to_intervals, workouts)
        except Exception as e:
            log.exception("upload failed")
            await msg.reply_text(f"Upload failed: {e}")
            return

    await msg.reply_text("Done. Workouts should sync to Suunto shortly.")


async def health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def telegram_webhook(request: web.Request) -> web.Response:
    """Ack Telegram immediately, then process. Slow handlers must not block the 200."""
    app: Application = request.app["bot_app"]
    data = await request.json()
    update = Update.de_json(data, app.bot)
    if update is None:
        return web.Response(text="ok")

    uid = update.update_id
    if uid in _seen_update_ids:
        log.info("Ignoring duplicate update_id=%s", uid)
        return web.Response(text="ok")
    _seen_update_ids.add(uid)
    if len(_seen_update_ids) > 500:
        _seen_update_ids.clear()

    async def _run() -> None:
        try:
            await app.process_update(update)
        except Exception:
            log.exception("process_update failed for update_id=%s", uid)

    asyncio.create_task(_run())
    return web.Response(text="ok")


async def on_startup(web_app: web.Application) -> None:
    bot_app: Application = web_app["bot_app"]
    await bot_app.initialize()
    await bot_app.start()
    if PUBLIC_URL:
        webhook = f"{PUBLIC_URL}/telegram"
        await bot_app.bot.set_webhook(url=webhook, drop_pending_updates=True)
        log.info("Webhook set to %s", webhook)
    else:
        log.info("No PUBLIC_URL/RENDER_EXTERNAL_URL — use local polling mode instead")


async def on_cleanup(web_app: web.Application) -> None:
    bot_app: Application = web_app["bot_app"]
    if PUBLIC_URL:
        await bot_app.bot.delete_webhook()
    await bot_app.stop()
    await bot_app.shutdown()


def build_bot_app() -> Application:
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    return bot_app


def run_webhook_server() -> None:
    bot_app = build_bot_app()
    web_app = web.Application()
    web_app["bot_app"] = bot_app
    web_app.router.add_get("/health", health)
    web_app.router.add_get("/", health)
    web_app.router.add_post("/telegram", telegram_webhook)
    web_app.on_startup.append(on_startup)
    web_app.on_cleanup.append(on_cleanup)
    log.info("Starting webhook server on 0.0.0.0:%s for %s", PORT, RUNNER_NAME)
    web.run_app(web_app, host="0.0.0.0", port=PORT)


def run_polling() -> None:
    bot_app = build_bot_app()
    log.info("Starting polling bot for %s", RUNNER_NAME)
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    if PUBLIC_URL:
        run_webhook_server()
    else:
        run_polling()
