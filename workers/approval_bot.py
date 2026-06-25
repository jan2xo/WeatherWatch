import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PENDING_FILE = Path("output/pending_posts.json")


def load_pending():
    if not PENDING_FILE.exists():
        return {}
    return json.loads(PENDING_FILE.read_text())


def save_pending(data):
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(data, indent=2))


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = load_pending()

    if not context.args:
        await update.message.reply_text("Use: /approve JOB_ID")
        return

    job_id = context.args[0]

    if job_id not in pending:
        await update.message.reply_text(f"Job not found: {job_id}")
        return

    job = pending[job_id]
    job["status"] = "approved"
    pending[job_id] = job
    save_pending(pending)

    await update.message.reply_text(
        f"✅ Approved: {job_id}\n\nReady for Facebook publishing."
    )


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = load_pending()

    if not context.args:
        await update.message.reply_text("Use: /reject JOB_ID")
        return

    job_id = context.args[0]

    if job_id not in pending:
        await update.message.reply_text(f"Job not found: {job_id}")
        return

    job = pending[job_id]
    job["status"] = "rejected"
    pending[job_id] = job
    save_pending(pending)

    await update.message.reply_text(f"❌ Rejected: {job_id}")


async def modify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = load_pending()

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use:\n/modify JOB_ID CAPTION: your new caption here"
        )
        return

    job_id = context.args[0]
    new_text = " ".join(context.args[1:])

    if new_text.upper().startswith("CAPTION:"):
        new_text = new_text[8:].strip()

    if job_id not in pending:
        await update.message.reply_text(f"Job not found: {job_id}")
        return

    job = pending[job_id]
    job["caption"] = new_text
    job["status"] = "modified"
    pending[job_id] = job
    save_pending(pending)

    await update.message.reply_text(
        f"✏️ Caption modified: {job_id}\n\n{new_text}"
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("modify", modify))

    print("WeatherWatch approval bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()