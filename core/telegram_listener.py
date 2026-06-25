import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from core.app import WeatherWatch
from services.image_service import run_image_job
from services.telegram_service import run_telegram_job
from storage.approval_store import (
    get_current_job,
    approve_current_job,
    reject_current_job,
    update_current_job,
)

load_dotenv()


def parse_modify_text(text: str):
    text = text.replace("/modify", "", 1).strip()
    result = {}

    upper = text.upper()
    headline_index = upper.find("HEADLINE:")
    caption_index = upper.find("CAPTION:")

    if headline_index != -1:
        start = headline_index + len("HEADLINE:")
        end = caption_index if caption_index != -1 and caption_index > headline_index else len(text)
        headline = text[start:end].strip()
        if headline:
            result["headline"] = headline

    if caption_index != -1:
        start = caption_index + len("CAPTION:")
        end = headline_index if headline_index != -1 and headline_index > caption_index else len(text)
        caption = text[start:end].strip()
        if caption:
            result["caption"] = caption

    return result


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("WeatherWatch bot is online. 🦾")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = get_current_job()

    if not job:
        await update.message.reply_text(
            "WeatherWatch Service: RUNNING ✅\n\nNo current job."
        )
        return

    await update.message.reply_text(
        "WeatherWatch Service: RUNNING ✅\n\n"
        f"Current Job: {job['job_id']}\n"
        f"Status: {job['status']}\n"
        f"Provider: {job.get('provider')}\n"
        f"Source: {job.get('source')}\n\n"
        f"Headline:\n{job.get('headline')}\n\n"
        f"Caption:\n{job.get('caption')}"
    )


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌦 Fetching the latest weather data...")

    try:
        await asyncio.to_thread(WeatherWatch().update)
        await update.message.reply_text(
            "✅ Weather update generated and sent for approval."
        )

    except Exception as error:
        await update.message.reply_text(f"⚠️ Update failed.\n\n{error}")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = approve_current_job()

    if not job:
        await update.message.reply_text("No current job to approve.")
        return

    await update.message.reply_text(
        f"✅ Approved current job: {job['job_id']}\n\n"
        "Publishing to Facebook..."
    )

    try:
        from services.facebook_service import publish_current_job

        result = await asyncio.to_thread(publish_current_job)

        await update.message.reply_text(
            "🚀 Published to Facebook.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )

    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Approved, but Facebook publish failed.\n\n{error}"
        )


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = reject_current_job()

    if not ok:
        await update.message.reply_text("No current job to reject.")
        return

    await update.message.reply_text("❌ Current job rejected and moved to history.")


async def modify_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.caption or message.text or ""

    if not text.strip().startswith("/modify"):
        return

    current = get_current_job()

    if not current:
        await message.reply_text("No current job to modify.")
        return

    updates = parse_modify_text(text)

    if message.photo:
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        output_dir = Path("output/manual_inputs")
        output_dir.mkdir(parents=True, exist_ok=True)

        image_path = output_dir / f"{current['job_id']}_manual.jpg"
        await file.download_to_drive(str(image_path))

        updates["raw_image"] = str(image_path)

    if not updates:
        await message.reply_text(
            "Nothing to modify.\n\n"
            "Use:\n"
            "/modify\n"
            "HEADLINE: new headline\n"
            "CAPTION: new caption\n\n"
            "You may also attach a photo with the same caption."
        )
        return

    job = update_current_job(updates)

    rerender_needed = "headline" in updates or "raw_image" in updates

    if rerender_needed:
        image_job = {
            "raw_output_path": job["raw_image"],
            "final_output_path": job["image"],
            "headline": job["headline"],
            "source": job["source"],
        }

        await asyncio.to_thread(run_image_job, image_job)

    preview_job = {
        "final_output_path": job["image"],
        "caption": (
            "✏️ <b>Modified Preview</b>\n\n"
            f"<b>Headline:</b>\n{job.get('headline')}\n\n"
            f"<b>Caption:</b>\n{job.get('caption')}\n\n"
            "<b>Commands:</b>\n"
            "/approve\n"
            "/reject\n"
            "/modify\n"
            "HEADLINE: ...\n"
            "CAPTION: ..."
        ),
    }

    await asyncio.to_thread(run_telegram_job, preview_job)
    await message.reply_text("✅ Modification applied.")


def build_telegram_app():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))

    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, modify_message_handler))

    return app