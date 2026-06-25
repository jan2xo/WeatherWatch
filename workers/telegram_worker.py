import os
import requests
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


def run_telegram_job(job):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env")

    if not chat_id:
        raise ValueError("Missing TELEGRAM_CHAT_ID in .env")

    image_path = Path(job["final_output_path"])

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    caption = job.get("caption", "WeatherWatch update ready for review.")

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    with image_path.open("rb") as image_file:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={
                "photo": image_file,
            },
            timeout=30,
        )

    if not response.ok:
        raise RuntimeError(f"Telegram failed: {response.text}")

    return response.json()