import re
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
from services.facebook_admin_service import get_admin_connect_url
from services.facebook_service import (
    check_facebook_token_health,
    get_facebook_status,
    publish_current_job,
    save_manual_page_access_token,
)
from config.settings import (
    get_required_env,
    parse_env_id_list,
)
from storage.approval_store import (
    get_current_job,
    approve_current_job,
    reject_current_job,
    update_current_job,
)

load_dotenv()


MAX_DERIVED_HEADLINE_LENGTH = 70
UNAUTHORIZED_MESSAGE = "Unauthorized."
MODIFY_HELP_TEXT = (
    "<b>Modify Help:</b>\n"
    "/modify + full caption updates the Facebook/Instagram caption and derives the GPX headline from the first line.\n"
    "/modify HEADLINE: updates only the GPX graphic headline.\n"
    "/modify HEADLINE: + CAPTION: lets you override the GPX headline while using a separate Facebook caption.\n"
    "Attach a photo with /modify to replace the image.\n"
    "HEADLINE: affects only the graphic. It does not change the Facebook caption unless CAPTION: is also supplied."
)


def strip_command(text: str) -> str:
    return re.sub(r"^\s*/modify(?:@\w+)?", "", text, count=1, flags=re.IGNORECASE).strip()


def has_modify_command(text: str) -> bool:
    return re.match(r"^\s*/modify(?:@\w+)?(?:\s|$)", text or "", re.IGNORECASE) is not None


def get_sender_ids(update: Update):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message:
        chat = message.chat
        user = message.from_user

    chat_id = chat.id if chat else None
    user_id = user.id if user else None

    return chat_id, user_id


def is_authorized(update: Update) -> bool:
    chat_id, user_id = get_sender_ids(update)
    allowed_chat_ids = parse_env_id_list("TELEGRAM_ALLOWED_CHAT_IDS", required=True)
    allowed_user_ids = parse_env_id_list("TELEGRAM_ALLOWED_USER_IDS")

    if chat_id not in allowed_chat_ids:
        return False

    if allowed_user_ids and user_id not in allowed_user_ids:
        return False

    return True


async def reply_unauthorized(update: Update):
    message = update.effective_message

    if message:
        await message.reply_text(UNAUTHORIZED_MESSAGE)


def admin_command(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            await reply_unauthorized(update)
            return

        await handler(update, context)

    return wrapped


def normalize_headline_words(text: str) -> str:
    words = []

    for word in text.split():
        if word.startswith("#"):
            words.append(word)
        else:
            words.append(word.upper())

    return " ".join(words)


def clean_opener_for_headline(opener: str) -> str:
    opener = opener.strip()

    # Remove common emojis / symbols at the start
    opener = re.sub(r"^[^\w#]+", "", opener).strip()

    # Remove ending punctuation
    opener = opener.rstrip("!?.。").strip()

    # Collapse spaces
    opener = " ".join(opener.split())

    return normalize_headline_words(opener)


def format_hashtag_headline(headline: str) -> str:
    words = headline.split()
    hashtag_index = next(
        (index for index, word in enumerate(words) if word.startswith("#")),
        -1,
    )

    if hashtag_index == -1:
        return ""

    before_hashtag = " ".join(words[:hashtag_index]).strip()
    hashtag = words[hashtag_index].strip()
    after_hashtag = " ".join(words[hashtag_index + 1:]).strip()

    lines = []

    if before_hashtag:
        lines.append(before_hashtag)

    lines.append(hashtag)

    if after_hashtag:
        lines.append(after_hashtag)

    return "\n".join(lines)


def format_gpx_headline(headline: str) -> str:
    headline = clean_opener_for_headline(headline)

    if not headline:
        return ""

    if len(headline) > MAX_DERIVED_HEADLINE_LENGTH:
        return ""

    hashtag_headline = format_hashtag_headline(headline)

    if hashtag_headline:
        return hashtag_headline

    # Prefer comma as natural break
    if "," in headline:
        first, rest = headline.split(",", 1)
        return f"{first.strip()},\n{rest.strip()}"

    # Otherwise split near middle if long
    if len(headline) > 30:
        words = headline.split()
        mid = len(words) // 2

        first = " ".join(words[:mid])
        second = " ".join(words[mid:])

        return f"{first}\n{second}"

    return headline


def format_explicit_gpx_headline(headline: str) -> str:
    lines = [
        clean_opener_for_headline(line)
        for line in headline.splitlines()
        if line.strip()
    ]

    if len(lines) == 1:
        return format_gpx_headline(lines[0])

    return "\n".join(line for line in lines if line)


def extract_headline_from_caption(caption: str) -> str:
    lines = [line.strip() for line in caption.splitlines() if line.strip()]

    if not lines:
        return ""

    first_line = lines[0]
    return format_gpx_headline(first_line)


def parse_labeled_modify_text(text: str):
    text = strip_command(text)
    result = {}
    labels = list(re.finditer(r"(?im)^\s*(HEADLINE|CAPTION)\s*:\s*", text))

    for index, match in enumerate(labels):
        label = match.group(1).lower()
        start = match.end()
        end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
        value = text[start:end].strip()

        if not value:
            continue

        if label == "headline":
            result["headline"] = format_explicit_gpx_headline(value)

        if label == "caption":
            result["caption"] = value

    return result


def parse_modify_text(text: str):
    raw = strip_command(text)

    if not raw:
        return {}

    # Old supported format:
    # /modify
    # HEADLINE: ...
    # CAPTION: ...
    if "HEADLINE:" in raw.upper() or "CAPTION:" in raw.upper():
        return parse_labeled_modify_text(text)

    # New mobile-friendly format:
    # /modify
    # 🌀 OPENER HERE!
    #
    # UPDATE: ...
    return {
        "caption": raw
    }


def build_preview_caption(job):
    facebook_caption = job.get("captions", {}).get("facebook") or job.get("caption", "")

    return (
        "✏️ <b>Modified Preview</b>\n\n"
        f"<b>GPX Headline:</b>\n{job.get('headline')}\n\n"
        f"<b>Facebook Caption Preview:</b>\n{facebook_caption}\n\n"
        "<b>Commands:</b>\n"
        "/manual\n"
        "/approve\n"
        "/reject\n"
        "/retry_publish\n"
        "/fbstatus\n"
        "/fb_reconnect\n"
        "/fb_set_token\n\n"
        f"{MODIFY_HELP_TEXT}\n\n"
        "<b>Example:</b>\n"
        "/modify\n"
        "🌀 YOUR OPENER HERE!\n\n"
        "UPDATE: ..."
    )


def format_provider_display(job):
    return (
        job.get("provider_display")
        or job.get("provider_url")
        or job.get("provider")
        or "Provider"
    ).upper()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("WeatherWatch bot is online. 🦾")


async def manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "WeatherWatch Manual\n\n"
        "Basic:\n"
        "/start - Check if the bot is online.\n"
        "/status - Show the current WeatherWatch job and caption preview.\n\n"
        "Admin update flow:\n"
        "/update - Generate a new weather update and send it for approval.\n"
        "/approve - Approve the current job and publish it to Facebook.\n"
        "/reject - Reject the current job and move it to history.\n"
        "/retry_publish - Retry Facebook publishing for approved or publish_failed jobs.\n"
        "/fbstatus - Show Facebook token and publish status without exposing tokens.\n\n"
        "Facebook token management:\n"
        "/fb_reconnect - Get the local Facebook OAuth reconnect URL.\n"
        "/fb_set_token PAGE_ACCESS_TOKEN - Manually save a Page token fallback. Use only in a private admin chat.\n\n"
        "Modify examples:\n"
        "/modify + full caption - Updates Facebook/Instagram caption and derives GPX headline from the first line.\n\n"
        "/modify\n"
        "HEADLINE:\n"
        "CUSTOM GPX HEADLINE\n\n"
        "Updates only the GPX graphic headline.\n\n"
        "/modify\n"
        "HEADLINE:\n"
        "CUSTOM GPX HEADLINE\n\n"
        "CAPTION:\n"
        "your Facebook caption here\n\n"
        "Uses separate GPX headline and Facebook caption.\n\n"
        "Photo fallback:\n"
        "Attach a photo with /modify to replace the raw image and regenerate the GPX graphic."
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = get_current_job()

    if not job:
        await update.message.reply_text(
            "WeatherWatch Service: RUNNING ✅\n\nNo current job."
        )
        return

    facebook_caption = job.get("captions", {}).get("facebook") or job.get("caption", "")

    await update.message.reply_text(
        "WeatherWatch Service: RUNNING ✅\n\n"
        f"Current Job: {job['job_id']}\n"
        f"Status: {job['status']}\n"
        f"Provider: {format_provider_display(job)}\n"
        f"Source: {job.get('source')}\n\n"
        f"GPX Headline:\n{job.get('headline')}\n\n"
        f"Facebook Caption:\n{facebook_caption}"
    )


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌦 Fetching the latest weather data...")

    try:
        result = await asyncio.to_thread(WeatherWatch().update)

        if isinstance(result, dict) and result.get("skipped"):
            current_job = result.get("current_job", {})
            await update.message.reply_text(
                "⏭ Weather update skipped.\n\n"
                f"Current job: {current_job.get('job_id')}\n"
                f"Status: {current_job.get('status')}\n\n"
                "Use /approve, /reject, /retry_publish, or /fbstatus first."
            )
            return

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
        result = await asyncio.to_thread(publish_current_job)

        await update.message.reply_text(
            "🚀 Published to Facebook.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )

    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Approved, but Facebook publish failed.\n\n{error}"
        )


async def retry_publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = get_current_job()

    if not job:
        await update.message.reply_text("No current job to publish.")
        return

    if job.get("status") not in {"approved", "publish_failed"}:
        await update.message.reply_text(
            f"Current job is not ready for retry. Status: {job.get('status')}"
        )
        return

    await update.message.reply_text(
        f"🔁 Retrying Facebook publish for job: {job['job_id']}"
    )

    try:
        result = await asyncio.to_thread(publish_current_job)

        await update.message.reply_text(
            "🚀 Published to Facebook.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )

    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Facebook publish failed.\n\n{error}"
        )


async def fbstatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        token_status = await asyncio.to_thread(check_facebook_token_health)
    except Exception:
        token_status = get_facebook_status()

    job = get_current_job()
    lines = [
        "Facebook Status",
        f"Configured Page ID: {token_status.get('configured_page_id')}",
        f"Token source: {token_status.get('source')}",
        f"Page name: {token_status.get('page_name') or 'Unknown'}",
        f"Token status: {token_status.get('status')}",
        f"Last checked: {token_status.get('last_checked') or 'Never'}",
        f"Last updated: {token_status.get('last_updated') or 'Never'}",
    ]

    if token_status.get("last_error"):
        lines.append(f"Last token error: {token_status.get('last_error')}")

    if job:
        lines.extend([
            "",
            "Current Job",
            f"Job ID: {job.get('job_id')}",
            f"Status: {job.get('status')}",
        ])

        if job.get("facebook_post_id"):
            lines.append(f"Post ID: {job.get('facebook_post_id')}")

        if job.get("last_error"):
            lines.append(f"Last publish error: {job.get('last_error')}")

    await update.message.reply_text("\n".join(lines))


async def fb_reconnect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reconnect_url = get_admin_connect_url()
    except Exception as error:
        await update.message.reply_text(f"Facebook reconnect is not configured: {error}")
        return

    await update.message.reply_text(
        "Open this URL on the WeatherWatch machine to reconnect Facebook:\n\n"
        f"{reconnect_url}"
    )


async def fb_set_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    token = " ".join(context.args).strip()

    if message:
        try:
            await message.delete()
        except Exception:
            pass

    if not token:
        await update.effective_chat.send_message(
            "Send the manually-created Page access token like this:\n\n"
            "/fb_set_token PAGE_ACCESS_TOKEN\n\n"
            "Use a private admin chat. The token will not be echoed back."
        )
        return

    try:
        result = await asyncio.to_thread(save_manual_page_access_token, token)
    except Exception as error:
        await update.effective_chat.send_message(
            "⚠️ Facebook Page token was not saved.\n\n"
            f"{error}"
        )
        return

    await update.effective_chat.send_message(
        "✅ Facebook Page token saved.\n\n"
        f"Page: {result.get('page_name') or result.get('page_id')}\n"
        f"Source: {result.get('source')}\n"
        f"Status: {result.get('status')}"
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

    if not has_modify_command(text):
        return

    if not is_authorized(update):
        await reply_unauthorized(update)
        return

    current = get_current_job()

    if not current:
        await message.reply_text("No current job to modify.")
        return

    updates = parse_modify_text(text)
    warnings = []

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
            "Use one of these:\n"
            "/modify\n"
            "🌀 YOUR OPENER HERE!\n\n"
            "UPDATE: your caption here\n\n"
            "/modify\n"
            "HEADLINE:\n"
            "CUSTOM GPX HEADLINE\n\n"
            "/modify\n"
            "HEADLINE:\n"
            "CUSTOM GPX HEADLINE\n\n"
            "CAPTION:\n"
            "your Facebook caption here\n\n"
            "Attach a photo with /modify to replace the image.\n"
            "HEADLINE: modifies only the GPX graphic headline."
        )
        return

    # If the user supplied a clean caption without HEADLINE:, derive the GPX
    # headline from the first line. HEADLINE: always bypasses opener extraction.
    if "caption" in updates and "headline" not in updates:
        derived_headline = extract_headline_from_caption(updates["caption"])

        if derived_headline:
            updates["headline"] = derived_headline
        else:
            warnings.append(
                "⚠️ Caption updated, but GPX headline was not changed because the opener is empty or too long."
            )

    # If user modified caption, this becomes the final Facebook caption.
    if "caption" in updates:
        updates["captions"] = {
            "telegram": updates["caption"],
            "facebook": updates["caption"],
            "instagram": updates["caption"],
        }

    rerender_needed = "headline" in updates or "raw_image" in updates

    job = update_current_job(updates)

    if not job:
        await message.reply_text("No current job to modify.")
        return

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
        "caption": build_preview_caption(job),
    }

    await asyncio.to_thread(run_telegram_job, preview_job)

    reply = "✅ Modification applied."

    if warnings:
        reply += "\n\n" + "\n".join(warnings)

    await message.reply_text(reply)


def build_telegram_app():
    token = get_required_env("TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("manual", admin_command(manual_command)))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("update", admin_command(update_command)))
    app.add_handler(CommandHandler("approve", admin_command(approve_command)))
    app.add_handler(CommandHandler("reject", admin_command(reject_command)))
    app.add_handler(CommandHandler("retry_publish", admin_command(retry_publish_command)))
    app.add_handler(CommandHandler("fbstatus", admin_command(fbstatus_command)))
    app.add_handler(CommandHandler("fb_reconnect", admin_command(fb_reconnect_command)))
    app.add_handler(CommandHandler("fb_set_token", admin_command(fb_set_token_command)))

    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, modify_message_handler))

    return app
