import requests
from pathlib import Path

from config.settings import get_required_env, parse_env_id_list


TELEGRAM_PHOTO_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def get_telegram_config():
    bot_token = get_required_env("TELEGRAM_BOT_TOKEN").strip()
    raw_chat_id = get_required_env("TELEGRAM_CHAT_ID").strip()

    try:
        chat_id = int(raw_chat_id)
    except ValueError as error:
        raise ValueError("TELEGRAM_CHAT_ID must be a numeric Telegram chat ID") from error

    allowed_chat_ids = parse_env_id_list(
        "TELEGRAM_ALLOWED_CHAT_IDS",
        required=True,
    )
    if chat_id not in allowed_chat_ids:
        raise ValueError(
            "TELEGRAM_CHAT_ID must also be present in TELEGRAM_ALLOWED_CHAT_IDS"
        )

    return bot_token, str(chat_id)


def telegram_request(method, url, **kwargs):
    try:
        response = method(url, **kwargs)
    except requests.RequestException as error:
        raise RuntimeError(
            f"Telegram request failed: {error.__class__.__name__}"
        ) from None

    if not response.ok:
        raise RuntimeError(
            f"Telegram request failed: HTTP {response.status_code}"
        )

    return response


def split_telegram_text(text: str):
    chunks = []
    remaining = text

    while len(remaining) > TELEGRAM_MESSAGE_LIMIT:
        split_at = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)

        if split_at <= 0:
            split_at = TELEGRAM_MESSAGE_LIMIT

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def send_telegram_message(text: str):
    bot_token, chat_id = get_telegram_config()
    results = []

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for chunk in split_telegram_text(text):
        response = telegram_request(
            requests.post,
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
            },
            timeout=30,
        )

        results.append(response.json())

    return results[-1] if len(results) == 1 else results


def run_telegram_job(job):
    bot_token, chat_id = get_telegram_config()

    image_path = Path(job["final_output_path"])

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    caption = job.get("caption", "WeatherWatch update ready for review.")
    photo_caption = caption

    if len(caption) > TELEGRAM_PHOTO_CAPTION_LIMIT:
        photo_caption = "WeatherWatch update generated. Full approval preview follows."

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    with image_path.open("rb") as image_file:
        response = telegram_request(
            requests.post,
            url,
            data={
                "chat_id": chat_id,
                "caption": photo_caption,
                "parse_mode": "HTML",
            },
            files={
                "photo": image_file,
            },
            timeout=30,
        )

    result = response.json()

    if photo_caption != caption:
        return {
            "photo": result,
            "message": send_telegram_message(caption),
        }

    return result
