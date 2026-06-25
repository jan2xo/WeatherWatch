import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("WeatherWatch bot is online. 🦾")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("WeatherWatch Service: RUNNING ✅")


def build_telegram_app():
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))

    return app