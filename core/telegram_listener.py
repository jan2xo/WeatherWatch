import re
import asyncio
import io
import json
import html
import uuid
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
from services.image_rendering_service import (
    CONFIG_PATH as IMAGE_RENDERING_CONFIG_PATH,
    MAX_IMAGE_RENDERING_UPLOAD_BYTES,
    SUPPORTED_FIT_MODES,
    UPLOAD_DIR as IMAGE_RENDERING_UPLOAD_DIR,
    config_json_preview,
    get_image_rendering_status,
    load_config_file as load_image_rendering_config_file,
    reload_config as reload_image_rendering_config,
    replace_config_from_file as replace_image_rendering_config_from_file,
    render_manual_image,
    set_fit_mode,
    starter_config_json,
)
from services.telegram_service import run_telegram_job
from services.facebook_admin_service import get_admin_connect_url
from services.facebook_service import (
    check_facebook_token_health,
    get_facebook_status,
    publish_current_job,
    save_manual_page_access_token,
)
from services.caption_template_service import (
    TEMPLATE_PATH,
    get_template_status,
    reload_templates,
    replace_template_from_file,
    starter_template_json,
    template_json_preview,
    validate_template_file,
    MAX_TEMPLATE_UPLOAD_BYTES,
)
from services.content_composer_config_service import (
    CONFIG_PATH as COMPOSER_CONFIG_PATH,
    MAX_COMPOSER_UPLOAD_BYTES,
    UPLOAD_DIR as COMPOSER_UPLOAD_DIR,
    composer_json_preview,
    get_composer_status,
    reload_composer_config,
    replace_composer_config_from_file,
    starter_composer_json,
    load_composer_config_file,
)
from config.settings import (
    get_required_env,
    parse_env_id_list,
)
from storage.file_retention import cleanup_manual_inputs
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


def current_job_caption_preview(job, limit=900):
    facebook_caption = (
        job.get("captions", {}).get("facebook")
        or job.get("caption")
        or ""
    )

    if len(facebook_caption) > limit:
        return facebook_caption[:limit].rstrip() + "\n... shortened ..."

    return facebook_caption


async def send_job_preview(update: Update, job, caption):
    image_path = job.get("image")

    if image_path and Path(image_path).exists():
        await asyncio.to_thread(run_telegram_job, {
            "final_output_path": image_path,
            "caption": caption,
        })
        return

    await update.message.reply_text(caption)


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
        "Attach a photo with /modify to replace the raw image and regenerate the GPX graphic.\n\n"
        "Template tools:\n"
        "Use /template_manual for caption template editing, validation, upload, and reload commands.\n\n"
        "Content composer tools:\n"
        "Use /composer_manual for editable weather wording and composer configuration.\n\n"
        "Image rendering tools:\n"
        "Use /image_manual for manual image fit and intelligent map framing configuration.\n\n"
        "VPS backup reminder:\n"
        "state/ is gitignored but must be backed up. Important files: state/approval_state.json and state/facebook_token_state.json."
    )


async def image_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Image Rendering Manual\n\n"
        "This configuration controls manual Telegram images and intelligent framing metadata for automatic weather maps.\n\n"
        "manual_image:\n"
        "Controls only user-submitted photos and screenshots. Available fit modes are stretch, smartfit, and crop.\n\n"
        "auto_map:\n"
        "Uses parsed PAGASA conditions to choose configured regions, zoom, and geographic pan offsets for automatic provider maps. pan_x adjusts longitude and pan_y adjusts latitude in degrees.\n\n"
        "Commands:\n"
        "/image_fit [stretch|smartfit|crop] - View or change manual fit only.\n"
        "/image_status - Show manual and auto-map configuration status.\n"
        "/image_show - Show the current JSON.\n"
        "/image_builder - Get starter JSON.\n"
        "/image_validate - Validate the saved JSON.\n"
        "/image_reload - Reload valid JSON without restarting.\n"
        "/image_upload - Upload replacement JSON as an attachment.\n\n"
        "Output remains 1080x1350. All commands are protected by the Telegram admin allowlist."
    )


def format_image_fit_status(status):
    modes = "\n".join(status["available_modes"])
    return (
        "Current Image Rendering\n\n"
        "Mode:\n"
        f"{status['fit_mode']}\n\n"
        "Canvas:\n"
        f"{status['target_width']}x{status['target_height']}\n\n"
        "Available Modes:\n"
        f"{modes}"
    )


def format_image_status(status):
    default = status.get("default_framing") or {}
    situations = ", ".join(status.get("framing_situations") or ()) or "None"
    return (
        "Image Rendering Status\n\n"
        f"Config: {status.get('config_path')}\n"
        f"Version: {status.get('version') or 'Unknown'}\n"
        f"Validation: {status.get('validation_status')}\n"
        f"Last loaded: {status.get('last_loaded') or 'Never'}\n"
        f"Last error: {status.get('last_validation_error') or 'None'}\n\n"
        f"Manual mode: {status.get('fit_mode')}\n"
        f"Manual canvas: {status.get('target_width')}x{status.get('target_height')}\n\n"
        f"Auto map enabled: {status.get('auto_map_enabled')}\n"
        f"Framing enabled: {status.get('framing_enabled')}\n"
        f"Default framing: {default.get('region_id')} at zoom {default.get('zoom')}\n"
        f"Situations: {situations}"
    )


async def image_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        format_image_status(get_image_rendering_status())
    )


async def image_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = config_json_preview()
    except Exception as error:
        await update.message.reply_text(
            f"Image rendering preview failed: {error}"
        )
        return

    await update.message.reply_text(
        f"<pre>{html.escape(text, quote=False)}</pre>",
        parse_mode="HTML",
    )


async def image_builder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = starter_config_json()
    document = io.BytesIO(text.encode("utf-8"))
    document.name = "image_rendering.starter.json"
    await update.message.reply_document(
        document=document,
        filename="image_rendering.starter.json",
        caption="Starter manual-image and auto-map configuration.",
    )


async def image_validate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        load_image_rendering_config_file(IMAGE_RENDERING_CONFIG_PATH)
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Image rendering validation failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Image rendering configuration is valid.")


async def image_reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reload_image_rendering_config()
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Image rendering reload failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Image rendering configuration reloaded.")


async def image_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n/image_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".json"):
        await message.reply_text(
            "Upload rejected. The attached file must be JSON."
        )
        return
    if (
        document.file_size
        and document.file_size > MAX_IMAGE_RENDERING_UPLOAD_BYTES
    ):
        await message.reply_text(
            "Image rendering upload rejected: file too large."
        )
        return

    temp_path = (
        IMAGE_RENDERING_UPLOAD_DIR
        / f"image_rendering_upload.{uuid.uuid4().hex}.json"
    )
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        status = await asyncio.to_thread(
            replace_image_rendering_config_from_file,
            temp_path,
        )
    except json.JSONDecodeError:
        await message.reply_text(
            "⚠️ Image rendering upload failed. JSON could not be parsed."
        )
        return
    except ValueError as error:
        await message.reply_text(
            f"⚠️ Image rendering upload failed.\n\n{error}"
        )
        return
    except Exception:
        await message.reply_text(
            "⚠️ Image rendering upload failed safely."
        )
        return
    finally:
        temp_path.unlink(missing_ok=True)

    await message.reply_text(
        "✅ Image rendering configuration uploaded and reloaded.\n\n"
        f"{format_image_status(status)}"
    )


async def image_fit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            format_image_fit_status(get_image_rendering_status())
        )
        return

    mode = context.args[0].strip().lower()

    if len(context.args) != 1 or mode not in SUPPORTED_FIT_MODES:
        await update.message.reply_text(
            "Unsupported mode. Use /image_fit stretch, /image_fit smartfit, or /image_fit crop."
        )
        return

    try:
        status = set_fit_mode(mode)
    except (OSError, ValueError):
        await update.message.reply_text(
            "Image rendering mode could not be saved. The current mode was not changed."
        )
        return

    await update.message.reply_text(
        "Image rendering mode updated.\n\n"
        f"Mode: {status['fit_mode']}\n"
        f"Canvas: {status['target_width']}x{status['target_height']}\n\n"
        "This applies to future manual Telegram image uploads."
    )


async def template_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Caption Template Manual\n\n"
        "Templates control deterministic PAGASA caption lines.\n"
        "Editing templates changes wording without editing Python code.\n\n"
        "Commands:\n"
        "/template_status - Show provider, version, language, modified time, and validation status.\n"
        "/template_show - Show current template JSON or a shortened preview.\n"
        "/template_builder - Show a starter JSON template to copy and edit.\n"
        "/template_validate - Validate the saved template without applying changes.\n"
        "/template_reload - Reload template JSON from disk. Restart should not be required if this succeeds.\n"
        "/template_upload - Upload edited JSON as a file attachment. The bot validates it before replacing the active template.\n\n"
        "Limits and safety:\n"
        "Uploads must be JSON and 100 KB or smaller. The bot writes only to fixed template folders.\n\n"
        "Required template keys:\n"
        "cyclone_location, cyclone_intensity, cyclone_movement, affected_system, source_line\n\n"
        "Required translation groups:\n"
        "weather_systems, movement_directions\n\n"
        "Composer configuration is separate. Use /composer_manual for editorial weather wording.\n\n"
        "VPS backup reminder:\n"
        "state/ is gitignored but must be backed up. Important files: state/approval_state.json and state/facebook_token_state.json."
    )


def format_template_status(status):
    lines = [
        "Caption Template Status",
        f"Provider: {status.get('provider') or 'Unknown'}",
        f"Version: {status.get('version') or 'Unknown'}",
        f"Language: {status.get('language') or 'Unknown'}",
        f"Last modified: {status.get('last_modified') or 'Unknown'}",
        f"Last loaded: {status.get('last_loaded') or 'Never'}",
        f"Validation: {status.get('validation_status')}",
        f"Backup count: {status.get('backup_count', 0)}",
    ]

    if status.get("last_validation_error"):
        lines.append(f"Last error: {status.get('last_validation_error')}")

    return "\n".join(lines)


async def template_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_template_status(get_template_status()))


async def template_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = template_json_preview()
    except Exception as error:
        await update.message.reply_text(f"Template preview failed: {error}")
        return

    await update.message.reply_text(f"<pre>{html.escape(text)}</pre>", parse_mode="HTML")


async def template_builder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = starter_template_json()
    except Exception as error:
        await update.message.reply_text(f"Template builder failed: {error}")
        return

    await update.message.reply_text(f"<pre>{html.escape(text)}</pre>", parse_mode="HTML")


async def template_validate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        validate_template_file(TEMPLATE_PATH)
    except Exception as error:
        await update.message.reply_text(f"⚠️ Template validation failed.\n\n{error}")
        return

    await update.message.reply_text("✅ Caption template is valid.")


async def template_reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reload_templates()
    except Exception as error:
        await update.message.reply_text(f"⚠️ Template reload failed.\n\n{error}")
        return

    await update.message.reply_text("✅ Caption template reloaded.")


async def template_upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n"
            "/template_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""

    if not filename.lower().endswith(".json"):
        await message.reply_text("Upload rejected. The attached file must be JSON.")
        return

    if document.file_size and document.file_size > MAX_TEMPLATE_UPLOAD_BYTES:
        await message.reply_text("Template upload rejected: file too large.")
        return

    temp_path = Path("data/template_uploads") / f"caption_template_upload.{uuid.uuid4().hex}.json"
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        status = await asyncio.to_thread(replace_template_from_file, temp_path)
    except json.JSONDecodeError:
        await message.reply_text("⚠️ Template upload failed. JSON could not be parsed.")
        return
    except ValueError as error:
        if str(error) == "Template upload rejected: file too large.":
            await message.reply_text("Template upload rejected: file too large.")
            return

        await message.reply_text(f"⚠️ Template upload failed.\n\n{error}")
        return
    except Exception as error:
        await message.reply_text(f"⚠️ Template upload failed.\n\n{error}")
        return

    await message.reply_text(
        "✅ Caption template uploaded and reloaded.\n\n"
        f"{format_template_status(status)}"
    )


async def composer_manual_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Content Composer Manual\n\n"
        "Composer configuration controls editorial weather wording and detection aliases. It is separate from PAGASA caption templates.\n\n"
        "Commands:\n"
        "/composer_status - Show configuration version, language, load time, and validation status.\n"
        "/composer_show - Show the active composer JSON or a shortened preview.\n"
        "/composer_builder - Show a starter composer JSON.\n"
        "/composer_validate - Validate the saved configuration without applying changes.\n"
        "/composer_reload - Reload valid composer configuration without restarting.\n"
        "/composer_upload - Attach an edited JSON file to validate, back up, replace, and reload it.\n\n"
        "Composer uploads must be JSON and no larger than 100 KB.\n"
        "Composer commands do not modify config/caption_templates.pagasa.json."
    )


def format_composer_status(status):
    lines = [
        "Content Composer Status",
        f"Config: {status.get('config_path')}",
        f"Version: {status.get('version') or 'Unknown'}",
        f"Language: {status.get('language') or 'Unknown'}",
        f"Last loaded: {status.get('last_loaded') or 'Never'}",
        f"Validation: {status.get('validation_status')}",
    ]

    if status.get("last_validation_error"):
        lines.append(f"Last error: {status['last_validation_error']}")

    return "\n".join(lines)


async def composer_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        format_composer_status(get_composer_status())
    )


async def composer_show_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        text = composer_json_preview()
    except Exception as error:
        await update.message.reply_text(
            f"Composer preview failed: {error}"
        )
        return

    await update.message.reply_text(
        f"<pre>{html.escape(text)}</pre>",
        parse_mode="HTML",
    )


async def composer_builder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    document = io.BytesIO(starter_composer_json().encode("utf-8"))
    document.name = "content_composer.starter.json"
    await update.message.reply_document(
        document=document,
        filename="content_composer.starter.json",
        caption="Starter content composer configuration.",
    )


async def composer_validate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        load_composer_config_file(COMPOSER_CONFIG_PATH)
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Composer validation failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Content composer configuration is valid.")


async def composer_reload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        reload_composer_config()
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Composer reload failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Content composer configuration reloaded.")


async def composer_upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n/composer_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""

    if not filename.lower().endswith(".json"):
        await message.reply_text(
            "Upload rejected. The attached file must be JSON."
        )
        return

    if document.file_size and document.file_size > MAX_COMPOSER_UPLOAD_BYTES:
        await message.reply_text("Composer upload rejected: file too large.")
        return

    temp_path = (
        COMPOSER_UPLOAD_DIR
        / f"content_composer_upload.{uuid.uuid4().hex}.json"
    )
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        status = await asyncio.to_thread(
            replace_composer_config_from_file,
            temp_path,
        )
    except json.JSONDecodeError:
        await message.reply_text(
            "⚠️ Composer upload failed. JSON could not be parsed."
        )
        return
    except ValueError as error:
        if str(error) == "Composer upload rejected: file too large.":
            await message.reply_text(
                "Composer upload rejected: file too large."
            )
            return

        await message.reply_text(
            f"⚠️ Composer upload failed.\n\n{error}"
        )
        return
    except Exception as error:
        await message.reply_text(
            f"⚠️ Composer upload failed.\n\n{error}"
        )
        return
    finally:
        temp_path.unlink(missing_ok=True)

    await message.reply_text(
        "✅ Content composer configuration uploaded and reloaded.\n\n"
        f"{format_composer_status(status)}"
    )


async def config_upload_document_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    caption = message.caption or ""

    if re.match(
        r"^\s*/composer_upload(?:@\w+)?(?:\s|$)",
        caption,
        re.IGNORECASE,
    ):
        handler = composer_upload_command
    elif re.match(
        r"^\s*/image_upload(?:@\w+)?(?:\s|$)",
        caption,
        re.IGNORECASE,
    ):
        handler = image_upload_command
    else:
        return

    if not is_authorized(update):
        await reply_unauthorized(update)
        return

    await handler(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = get_current_job()

    if not job:
        await update.message.reply_text(
            "WeatherWatch Service: RUNNING ✅\n\nNo current job."
        )
        return

    await send_job_preview(update, job, (
        "WeatherWatch Service: RUNNING ✅\n\n"
        f"Current Job: {job['job_id']}\n"
        f"Status: {job['status']}\n"
        f"Provider: {format_provider_display(job)}\n"
        f"Source: {job.get('source')}\n\n"
        f"GPX Headline:\n{job.get('headline')}\n\n"
        f"Facebook Caption Preview:\n{current_job_caption_preview(job)}"
    ))


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌦 Fetching the latest weather data...")

    try:
        result = await asyncio.to_thread(WeatherWatch().update)

        if isinstance(result, dict) and result.get("skipped"):
            current_job = result.get("current_job", {})
            skipped_caption = (
                "⏭ Weather update skipped.\n\n"
                f"Current job: {current_job.get('job_id')}\n"
                f"Status: {current_job.get('status')}\n"
                f"Provider: {format_provider_display(current_job)}\n\n"
                f"GPX Headline:\n{current_job.get('headline') or 'None'}\n\n"
                f"Facebook Caption Preview:\n{current_job_caption_preview(current_job) or 'None'}\n\n"
                "Use /approve, /reject, /modify, /retry_publish, or /fbstatus first."
            )
            await send_job_preview(update, current_job, skipped_caption)

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
        await send_job_preview(update, job, (
            f"Current job is not ready for retry. Status: {job.get('status')}"
        ))
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

    if job:
        await send_job_preview(update, job, "\n".join(lines))
        return

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
        await asyncio.to_thread(render_manual_image, image_path)

        updates["raw_image"] = str(image_path)
        cleanup_manual_inputs()

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
    app.add_handler(CommandHandler("image_manual", admin_command(image_manual_command)))
    app.add_handler(CommandHandler("image_fit", admin_command(image_fit_command)))
    app.add_handler(CommandHandler("image_status", admin_command(image_status_command)))
    app.add_handler(CommandHandler("image_show", admin_command(image_show_command)))
    app.add_handler(CommandHandler("image_builder", admin_command(image_builder_command)))
    app.add_handler(CommandHandler("image_validate", admin_command(image_validate_command)))
    app.add_handler(CommandHandler("image_reload", admin_command(image_reload_command)))
    app.add_handler(CommandHandler("image_upload", admin_command(image_upload_command)))
    app.add_handler(CommandHandler("template_manual", admin_command(template_manual_command)))
    app.add_handler(CommandHandler("template_status", admin_command(template_status_command)))
    app.add_handler(CommandHandler("template_show", admin_command(template_show_command)))
    app.add_handler(CommandHandler("template_builder", admin_command(template_builder_command)))
    app.add_handler(CommandHandler("template_validate", admin_command(template_validate_command)))
    app.add_handler(CommandHandler("template_reload", admin_command(template_reload_command)))
    app.add_handler(CommandHandler("template_upload", admin_command(template_upload_command)))
    app.add_handler(CommandHandler("composer_manual", admin_command(composer_manual_command)))
    app.add_handler(CommandHandler("composer_status", admin_command(composer_status_command)))
    app.add_handler(CommandHandler("composer_show", admin_command(composer_show_command)))
    app.add_handler(CommandHandler("composer_builder", admin_command(composer_builder_command)))
    app.add_handler(CommandHandler("composer_validate", admin_command(composer_validate_command)))
    app.add_handler(CommandHandler("composer_reload", admin_command(composer_reload_command)))
    app.add_handler(CommandHandler("composer_upload", admin_command(composer_upload_command)))

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            config_upload_document_handler,
        )
    )
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, modify_message_handler))

    return app
