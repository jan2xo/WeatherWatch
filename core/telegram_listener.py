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

from core.scheduler import (
    get_scheduler_runtime_status,
    refresh_scheduler,
)
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
    save_manual_page_access_token,
)
from services.control_plane_service import (
    approve_current_job as control_approve_current_job,
    generate_update,
    reject_current_job as control_reject_current_job,
    retry_publish as control_retry_publish,
    set_post_type as control_set_post_type,
    set_windy_layer as control_set_windy_layer,
    text_approve_current_job as control_text_approve_current_job,
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
from services.scheduler_config_service import (
    CONFIG_PATH as SCHEDULER_CONFIG_PATH,
    MAX_SCHEDULER_UPLOAD_BYTES,
    UPLOAD_DIR as SCHEDULER_UPLOAD_DIR,
    get_scheduler_status,
    load_scheduler_config_file,
    reload_scheduler_config,
    replace_scheduler_config_from_file,
    scheduler_json_preview,
    starter_scheduler_json,
)
from services.language_normalization_service import (
    CONFIG_PATH as LANGUAGE_CONFIG_PATH,
    MAX_LANGUAGE_UPLOAD_BYTES,
    UPLOAD_DIR as LANGUAGE_UPLOAD_DIR,
    get_language_status,
    language_json_preview,
    load_language_config_file,
    reload_language_config,
    replace_language_config_from_file,
    starter_language_json,
)
from services.windy_layer_service import (
    CONFIG_PATH as WINDY_CONFIG_PATH,
    MAX_WINDY_UPLOAD_BYTES,
    UPLOAD_DIR as WINDY_UPLOAD_DIR,
    get_windy_layer_status,
    load_windy_layer_config_file,
    reload_windy_layer_config,
    replace_windy_config_from_file,
    starter_windy_json,
    windy_json_preview,
)
from config.settings import (
    get_required_env,
    parse_env_id_list,
)
from storage.file_retention import cleanup_manual_inputs
from storage.approval_store import (
    get_current_job,
    update_current_job,
)

load_dotenv()


MAX_DERIVED_HEADLINE_LENGTH = 70
UNAUTHORIZED_MESSAGE = "Unauthorized."
MODIFY_LABEL_PATTERN = re.compile(
    r"^\s*(HEADLINES?|CAPTIONS?)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)
MODIFY_HELP_TEXT = (
    "<b>Modify Help:</b>\n"
    "/modify + full caption updates the Facebook/Instagram caption and derives the GPX headline from the first line.\n"
    "/modify HEADLINE: updates only the GPX graphic headline.\n"
    "/modify HEADLINE: + CAPTION: lets you override the GPX headline while using a separate Facebook caption.\n"
    "Attach a photo with /modify to replace the image.\n"
    "HEADLINE: affects only the graphic. It does not change the Facebook caption unless CAPTION: is also supplied."
)
IMAGE_FIT_INTENTS = {
    "image_fit_stretch": "stretch",
    "image_fit_smartfit": "smartfit",
    "image_fit_crop": "crop",
}
WINDY_LAYER_INTENTS = {
    "windy_layer_satellite": "satellite",
    "windy_layer_radar": "radar",
    "windy_layer_wind": "wind",
    "windy_layer_rain": "rain",
    "windy_layer_clouds": "clouds",
    "windy_layer_temperature": "temperature",
    "windy_layer_rain_accumulation": "rain_accumulation",
    "windy_layer_thunderstorms": "thunderstorms",
}
POST_TYPE_INTENTS = {
    "post_type_image": "image",
    "post_type_text": "text",
}


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
    labels = list(MODIFY_LABEL_PATTERN.finditer(text))

    for index, match in enumerate(labels):
        label = match.group(1).lower().removesuffix("s")
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
    if MODIFY_LABEL_PATTERN.search(raw):
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
    post_type_notice = (
        "<b>Facebook will publish this as a text-only post.</b>\n\n"
        if job.get("post_type", "image") == "text"
        else ""
    )
    windy_line = (
        f"<b>Windy Layer:</b> {job.get('windy_layer_label')}\n"
        if job.get("windy_layer_label")
        else ""
    )

    return (
        "✏️ <b>Modified Preview</b>\n\n"
        f"<b>Post Type:</b> {job.get('post_type', 'image').upper()}\n"
        f"{windy_line}"
        f"{post_type_notice}"
        f"<b>GPX Headline:</b>\n{job.get('headline')}\n\n"
        f"<b>Facebook Caption Preview:</b>\n{facebook_caption}\n\n"
        "<b>Commands:</b>\n"
        "/manual\n"
        "/post_type\n"
        "/approve\n"
        "/text_approve\n"
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
        "/text_approve - Approve the current job as a native Facebook text post.\n"
        "/reject - Reject the current job and move it to history.\n"
        "/retry_publish - Retry Facebook publishing for approved or publish_failed jobs.\n"
        "/post_type - Show the current post type.\n"
        "/post_type_image - Select image publishing.\n"
        "/post_type_text - Select native text publishing.\n"
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
        "Scheduler tools:\n"
        "Use /scheduler_manual for scheduled update configuration.\n\n"
        "Language tools:\n"
        "Use /language_manual for PAGASA phrase normalization.\n\n"
        "Windy tools:\n"
        "Use /windy_manual for Windy layer configuration and /windy_layer to view or select the current job layer.\n\n"
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
        "Uses parsed PAGASA conditions to choose configured regions, zoom, and geographic pan offsets for automatic provider maps. Affected-area routing is checked before generic weather-system defaults.\n\n"
        "Hierarchical area routing:\n"
        "Each region declares aliases and a parent_group: philippines, luzon, visayas, or mindanao. Dedicated center/zoom values are optional for subregions. A subregion without dedicated framing inherits its parent group. Multi-area forecasts combine parent groups automatically, so subregion combinations do not need to be listed individually. pan_x adjusts longitude and pan_y adjusts latitude in degrees.\n\n"
        "Commands:\n"
        "/image_fit - View the current manual fit mode.\n"
        "/image_fit_stretch - Use direct resize for future manual images.\n"
        "/image_fit_smartfit - Preserve ratio, cover, and center-crop.\n"
        "/image_fit_crop - Use a centered native-pixel crop.\n"
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
    area_aliases = ", ".join(status.get("area_routing_aliases") or ()) or "None"
    area_combinations = (
        ", ".join(status.get("area_routing_combinations") or ()) or "None"
    )
    fallback_regions = (
        ", ".join(status.get("parent_fallback_regions") or ()) or "None"
    )
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
        f"Area routing enabled: {status.get('area_routing_enabled')}\n"
        f"Default framing: {default.get('region_id')} at zoom {default.get('zoom')}\n"
        f"Situations: {situations}\n"
        f"Hierarchical regions: {status.get('hierarchical_region_count', 0)}\n"
        f"Regions with aliases: {area_aliases}\n"
        f"Parent combinations: {area_combinations}\n"
        f"Parent fallback regions: {fallback_regions}"
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
            "Unsupported mode. Use /image_fit_stretch, "
            "/image_fit_smartfit, or /image_fit_crop."
        )
        return

    await apply_image_fit_intent(
        update,
        mode,
        deprecated_alias=True,
    )


async def apply_image_fit_intent(
    update: Update,
    mode,
    deprecated_alias=False,
):
    try:
        status = set_fit_mode(mode)
    except (OSError, ValueError):
        await update.message.reply_text(
            "Image rendering mode could not be saved. The current mode was not changed."
        )
        return

    message = (
        "Image rendering mode updated.\n\n"
        f"Mode: {status['fit_mode']}\n"
        f"Canvas: {status['target_width']}x{status['target_height']}\n\n"
        "This applies to future manual Telegram image uploads."
    )
    if deprecated_alias:
        message += (
            "\n\nThis syntax is deprecated.\n"
            f"Use: /image_fit_{mode}"
        )
    await update.message.reply_text(message)


def image_fit_intent_command(mode):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await apply_image_fit_intent(update, mode)

    return handler


async def scheduler_manual_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Scheduler Manual\n\n"
        "Scheduler configuration controls automatic weather-update times without editing Python code.\n\n"
        "Each job has an ID, enabled state, 24-hour HH:MM time, action, provider field, and pending-job skip policy.\n"
        "When auto_reject_before_next_run is enabled, stale pending or modified jobs are rejected immediately before the next scheduled update. Approved and publishing jobs are never auto-rejected.\n"
        "Supported action: weather_update\n"
        "Timezone uses an IANA name such as Asia/Manila.\n\n"
        "Commands:\n"
        "/scheduler_status - Show scheduler health and enabled jobs.\n"
        "/scheduler_show - Show the active scheduler JSON.\n"
        "/scheduler_builder - Show starter scheduler JSON.\n"
        "/scheduler_validate - Validate the saved JSON.\n"
        "/scheduler_reload - Reload JSON and refresh registered jobs.\n"
        "/scheduler_upload - Upload, validate, back up, replace, and refresh scheduler JSON.\n\n"
        "Uploads must be JSON and no larger than 100 KB."
    )


def format_scheduler_status(status):
    runtime = get_scheduler_runtime_status()
    enabled_jobs = status.get("enabled_jobs") or []
    configured = ", ".join(
        f"{job['id']}@{job['time']}" for job in enabled_jobs
    ) or "None"
    next_runs = ", ".join(
        f"{job['id']}={job['next_run'] or 'pending'}"
        for job in runtime.get("registered_jobs", [])
    ) or "None"

    return (
        "Scheduler Status\n\n"
        f"Config: {status.get('config_path')}\n"
        f"Version: {status.get('version') or 'Unknown'}\n"
        f"Enabled: {status.get('enabled')}\n"
        f"Timezone: {status.get('timezone')}\n"
        f"Validation: {status.get('validation_status')}\n"
        f"Last loaded: {status.get('last_loaded') or 'Never'}\n"
        f"Last error: {status.get('last_validation_error') or 'None'}\n"
        f"Enabled jobs: {status.get('enabled_job_count', 0)}\n"
        f"Auto-reject before next run: {status.get('auto_reject_before_next_run')}\n"
        f"Auto-reject statuses: {', '.join(status.get('auto_reject_statuses') or []) or 'None'}\n"
        f"Configured: {configured}\n"
        f"Next runs: {next_runs}"
    )


async def scheduler_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        format_scheduler_status(get_scheduler_status())
    )


async def scheduler_show_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        text = scheduler_json_preview()
    except Exception as error:
        await update.message.reply_text(
            f"Scheduler preview failed: {error}"
        )
        return

    await update.message.reply_text(
        f"<pre>{html.escape(text, quote=False)}</pre>",
        parse_mode="HTML",
    )


async def scheduler_builder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        f"<pre>{html.escape(starter_scheduler_json(), quote=False)}</pre>",
        parse_mode="HTML",
    )


async def scheduler_validate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        load_scheduler_config_file(SCHEDULER_CONFIG_PATH)
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Scheduler validation failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Scheduler configuration is valid.")


async def scheduler_reload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        reload_scheduler_config()
        refresh_scheduler()
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Scheduler reload failed.\n\n{error}"
        )
        return

    await update.message.reply_text(
        "✅ Scheduler configuration reloaded and jobs refreshed.\n\n"
        f"{format_scheduler_status(get_scheduler_status())}"
    )


async def scheduler_upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n/scheduler_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".json"):
        await message.reply_text(
            "Upload rejected. The attached file must be JSON."
        )
        return
    if document.file_size and document.file_size > MAX_SCHEDULER_UPLOAD_BYTES:
        await message.reply_text("Scheduler upload rejected: file too large.")
        return

    temp_path = (
        SCHEDULER_UPLOAD_DIR
        / f"scheduler_upload.{uuid.uuid4().hex}.json"
    )
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        await asyncio.to_thread(
            replace_scheduler_config_from_file,
            temp_path,
        )
        refresh_scheduler()
    except json.JSONDecodeError:
        await message.reply_text(
            "⚠️ Scheduler upload failed. JSON could not be parsed."
        )
        return
    except ValueError as error:
        await message.reply_text(
            f"⚠️ Scheduler upload failed.\n\n{error}"
        )
        return
    except Exception:
        await message.reply_text("⚠️ Scheduler upload failed safely.")
        return
    finally:
        temp_path.unlink(missing_ok=True)

    await message.reply_text(
        "✅ Scheduler configuration uploaded and jobs refreshed.\n\n"
        f"{format_scheduler_status(get_scheduler_status())}"
    )


async def language_manual_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Language Normalization Manual\n\n"
        "Language normalization converts configured PAGASA area phrases before content composition.\n\n"
        "Forms:\n"
        "body - Preserves directional detail for caption prose.\n"
        "headline - Uses a concise region label for GPX headlines.\n"
        "short - Uses a compact label for future short surfaces.\n\n"
        "Commands:\n"
        "/language_status - Show configuration and phrase coverage status.\n"
        "/language_show - Show the current JSON or shortened preview.\n"
        "/language_builder - Download starter JSON.\n"
        "/language_validate - Validate the saved JSON.\n"
        "/language_reload - Reload valid JSON without restarting.\n"
        "/language_upload - Upload, validate, back up, replace, and reload JSON.\n\n"
        "Uploads must be JSON and no larger than 100 KB. Unknown phrases remain unchanged."
    )


def format_language_status(status):
    return (
        "Language Normalization Status\n\n"
        f"Config: {status.get('config_path')}\n"
        f"Version: {status.get('version') or 'Unknown'}\n"
        f"Language: {status.get('language') or 'Unknown'}\n"
        f"Phrases: {status.get('phrase_count', 0)}\n"
        f"Validation: {status.get('validation_status')}\n"
        f"Last loaded: {status.get('last_loaded') or 'Never'}\n"
        f"Last error: {status.get('last_validation_error') or 'None'}"
    )


async def language_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        format_language_status(get_language_status())
    )


async def language_show_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        text = language_json_preview()
    except Exception as error:
        await update.message.reply_text(
            f"Language preview failed: {error}"
        )
        return

    await update.message.reply_text(
        f"<pre>{html.escape(text, quote=False)}</pre>",
        parse_mode="HTML",
    )


async def language_builder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    document = io.BytesIO(starter_language_json().encode("utf-8"))
    document.name = "language_normalization.starter.json"
    await update.message.reply_document(
        document=document,
        filename="language_normalization.starter.json",
        caption="Starter PAGASA language normalization configuration.",
    )


async def language_validate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        load_language_config_file(LANGUAGE_CONFIG_PATH)
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Language validation failed.\n\n{error}"
        )
        return

    await update.message.reply_text(
        "✅ Language normalization configuration is valid."
    )


async def language_reload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        reload_language_config()
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Language reload failed.\n\n{error}"
        )
        return

    await update.message.reply_text(
        "✅ Language normalization configuration reloaded."
    )


async def language_upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message

    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n/language_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".json"):
        await message.reply_text(
            "Upload rejected. The attached file must be JSON."
        )
        return
    if document.file_size and document.file_size > MAX_LANGUAGE_UPLOAD_BYTES:
        await message.reply_text("Language upload rejected: file too large.")
        return

    temp_path = (
        LANGUAGE_UPLOAD_DIR
        / f"language_upload.{uuid.uuid4().hex}.json"
    )
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        status = await asyncio.to_thread(
            replace_language_config_from_file,
            temp_path,
        )
    except json.JSONDecodeError:
        await message.reply_text(
            "⚠️ Language upload failed. JSON could not be parsed."
        )
        return
    except ValueError as error:
        await message.reply_text(
            f"⚠️ Language upload failed.\n\n{error}"
        )
        return
    except Exception:
        await message.reply_text("⚠️ Language upload failed safely.")
        return
    finally:
        temp_path.unlink(missing_ok=True)

    await message.reply_text(
        "✅ Language normalization configuration uploaded and reloaded.\n\n"
        f"{format_language_status(status)}"
    )


async def windy_manual_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    status = get_windy_layer_status()
    available_layers = "\n".join(
        f"- {layer['id']} ({layer['label']})"
        for layer in status.get("enabled_layers", [])
    ) or "- None"

    await update.message.reply_text(
        "Windy Layer Manual\n\n"
        "Windy layers control the map visualization used before provider capture. Satellite is the recommended default.\n\n"
        "Suggestion rules may recommend a layer from forecast context, but rotation is disabled by default and WeatherWatch does not silently change the selected layer.\n\n"
        "Available layers:\n"
        f"{available_layers}\n\n"
        "Runtime:\n"
        "/windy_layer - Show the persistent default, current job, suggestion, and enabled layers.\n"
        "Selection commands save the default for future updates and update eligible current-job metadata. Existing graphics are not recaptured.\n\n"
        "Selection commands:\n"
        "/windy_layer_satellite\n"
        "/windy_layer_radar\n"
        "/windy_layer_wind\n"
        "/windy_layer_rain\n"
        "/windy_layer_temperature\n"
        "/windy_layer_clouds\n"
        "/windy_layer_rain_accumulation\n"
        "/windy_layer_thunderstorms\n\n"
        "Configuration:\n"
        "/windy_status - Show validation and enabled-layer status.\n"
        "/windy_show - Show current JSON or a shortened preview.\n"
        "/windy_builder - Download starter JSON.\n"
        "/windy_validate - Validate the saved JSON.\n"
        "/windy_reload - Reload valid JSON without restarting.\n"
        "/windy_upload - Upload, validate, back up, replace, and reload JSON.\n\n"
        "Uploads must be JSON and no larger than 100 KB."
    )


def format_windy_status(status):
    enabled = ", ".join(
        layer["id"] for layer in status.get("enabled_layers", [])
    ) or "None"
    disabled = ", ".join(
        layer["id"] for layer in status.get("disabled_layers", [])
    ) or "None"
    return (
        "Windy Layer Status\n\n"
        f"Config: {status.get('config_path')}\n"
        f"Version: {status.get('version') or 'Unknown'}\n"
        f"Validation: {status.get('validation_status')}\n"
        f"Last loaded: {status.get('last_loaded') or 'Never'}\n"
        f"Last error: {status.get('last_validation_error') or 'None'}\n"
        f"Default layer: {status.get('default_layer') or 'Unknown'}\n"
        f"Rotation enabled: {status.get('rotation_enabled')}\n"
        f"Enabled layers: {enabled}\n"
        f"Disabled layers: {disabled}"
    )


async def windy_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        format_windy_status(get_windy_layer_status())
    )


async def windy_show_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        text = windy_json_preview()
    except Exception as error:
        await update.message.reply_text(f"Windy preview failed: {error}")
        return

    await update.message.reply_text(
        f"<pre>{html.escape(text, quote=False)}</pre>",
        parse_mode="HTML",
    )


async def windy_builder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    document = io.BytesIO(starter_windy_json().encode("utf-8"))
    document.name = "windy_layers.starter.json"
    await update.message.reply_document(
        document=document,
        filename="windy_layers.starter.json",
        caption="Starter Windy layer configuration.",
    )


async def windy_validate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        load_windy_layer_config_file(WINDY_CONFIG_PATH)
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Windy validation failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Windy layer configuration is valid.")


async def windy_reload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        reload_windy_layer_config()
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Windy reload failed.\n\n{error}"
        )
        return

    await update.message.reply_text("✅ Windy layer configuration reloaded.")


async def windy_upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    if not message.document:
        await message.reply_text(
            "Attach a JSON file with this command:\n\n/windy_upload"
        )
        return

    document = message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".json"):
        await message.reply_text(
            "Upload rejected. The attached file must be JSON."
        )
        return
    if document.file_size and document.file_size > MAX_WINDY_UPLOAD_BYTES:
        await message.reply_text("Windy upload rejected: file too large.")
        return

    temp_path = WINDY_UPLOAD_DIR / f"windy_upload.{uuid.uuid4().hex}.json"
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(str(temp_path))
        status = await asyncio.to_thread(
            replace_windy_config_from_file,
            temp_path,
        )
    except json.JSONDecodeError:
        await message.reply_text(
            "⚠️ Windy upload failed. JSON could not be parsed."
        )
        return
    except ValueError as error:
        await message.reply_text(f"⚠️ Windy upload failed.\n\n{error}")
        return
    except Exception:
        await message.reply_text("⚠️ Windy upload failed safely.")
        return
    finally:
        temp_path.unlink(missing_ok=True)

    await message.reply_text(
        "✅ Windy layer configuration uploaded and reloaded.\n\n"
        f"{format_windy_status(status)}"
    )


async def windy_layer_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    job = get_current_job()

    if not context.args:
        status = get_windy_layer_status()
        enabled = ", ".join(
            layer["id"] for layer in status.get("enabled_layers", [])
        )
        text = (
            "Current Windy Layer\n\n"
            f"Default for future updates: {status.get('default_layer')}\n"
            f"Current job: {(job or {}).get('windy_layer') or 'None'}\n"
            f"Suggested: {(job or {}).get('suggested_windy_layer') or 'Unknown'}\n"
            f"Enabled: {enabled or 'None'}"
        )
        if job:
            await send_job_preview(update, job, text)
        else:
            await update.message.reply_text(text)
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Use an explicit command such as /windy_layer_satellite "
            "or /windy_layer_wind."
        )
        return

    await apply_windy_layer_intent(
        update,
        context.args[0],
        deprecated_alias=True,
    )


async def apply_windy_layer_intent(
    update: Update,
    layer_id,
    deprecated_alias=False,
):
    try:
        result = await asyncio.to_thread(
            control_set_windy_layer,
            layer_id,
        )
    except Exception as error:
        await update.message.reply_text(
            f"Windy layer was not changed.\n\n{error}"
        )
        return

    lines = [
        "✅ Windy default layer updated.",
        "",
        f"Default for future updates: {result['windy_layer']}",
        "This setting is saved and survives application restart.",
    ]
    if result.get("current_job_updated"):
        lines.extend([
            "",
            "Current job metadata was also updated.",
            f"URL: {result['windy_url']}",
            "The existing screenshot and final graphic were not recaptured.",
        ])
    elif result.get("job"):
        lines.extend([
            "",
            "The current job was not changed because it is not an editable Windy job.",
        ])
    if deprecated_alias:
        lines.extend([
            "",
            "This syntax is deprecated.",
            f"Use: /windy_layer_{result['windy_layer']}",
        ])

    await update.message.reply_text(
        "\n".join(lines),
    )


def windy_layer_intent_command(layer_id):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await apply_windy_layer_intent(update, layer_id)

    return handler


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
        "composer.weather_systems defines recurring PAGASA systems. Each system has a category, display name, aliases, headline template, and summary template.\n"
        "Configured defaults include Habagat, Amihan, ITCZ, LPA, Easterlies, Shear Line, and Frontal System.\n"
        "Cyclone wording and the general fallback remain separate composer sections.\n\n"
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
    systems = ", ".join(
        f"{system.get('display_name')} ({system.get('category')})"
        for system in status.get("weather_systems", [])
    ) or "None"
    lines = [
        "Content Composer Status",
        f"Config: {status.get('config_path')}",
        f"Version: {status.get('version') or 'Unknown'}",
        f"Language: {status.get('language') or 'Unknown'}",
        f"Last loaded: {status.get('last_loaded') or 'Never'}",
        f"Validation: {status.get('validation_status')}",
        f"Weather systems: {status.get('weather_system_count', 0)}",
        f"Configured: {systems}",
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
    elif re.match(
        r"^\s*/scheduler_upload(?:@\w+)?(?:\s|$)",
        caption,
        re.IGNORECASE,
    ):
        handler = scheduler_upload_command
    elif re.match(
        r"^\s*/language_upload(?:@\w+)?(?:\s|$)",
        caption,
        re.IGNORECASE,
    ):
        handler = language_upload_command
    elif re.match(
        r"^\s*/windy_upload(?:@\w+)?(?:\s|$)",
        caption,
        re.IGNORECASE,
    ):
        handler = windy_upload_command
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
        f"Post Type: {job.get('post_type', 'image').upper()}\n"
        f"Provider: {format_provider_display(job)}\n"
        f"Windy Layer: {job.get('windy_layer_label') or 'N/A'}\n"
        f"Source: {job.get('source')}\n\n"
        f"GPX Headline:\n{job.get('headline')}\n\n"
        f"Facebook Caption Preview:\n{current_job_caption_preview(job)}"
    ))


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌦 Fetching the latest weather data...")

    try:
        result = await asyncio.to_thread(generate_update)

        if isinstance(result, dict) and result.get("skipped"):
            current_job = result.get("current_job", {})
            skipped_caption = (
                "⏭ Weather update skipped.\n\n"
                f"Current job: {current_job.get('job_id')}\n"
                f"Status: {current_job.get('status')}\n"
                f"Post Type: {current_job.get('post_type', 'image').upper()}\n"
                f"Provider: {format_provider_display(current_job)}\n"
                f"Windy Layer: {current_job.get('windy_layer_label') or 'N/A'}\n\n"
                f"GPX Headline:\n{current_job.get('headline') or 'None'}\n\n"
                f"Facebook Caption Preview:\n{current_job_caption_preview(current_job) or 'None'}\n\n"
                "Use /approve, /text_approve, /reject, /modify, /retry_publish, or /fbstatus first."
            )
            await send_job_preview(update, current_job, skipped_caption)

            return

        await update.message.reply_text(
            "✅ Weather update generated and sent for approval."
        )

    except Exception as error:
        await update.message.reply_text(f"⚠️ Update failed.\n\n{error}")


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await asyncio.to_thread(control_approve_current_job)

        await update.message.reply_text(
            f"✅ Approved current job: {result.get('job_id')}\n\n"
            "🚀 Published to Facebook.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )

    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Approval or Facebook publish failed.\n\n{error}"
        )


async def text_approve_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        result = await asyncio.to_thread(
            control_text_approve_current_job
        )

        await update.message.reply_text(
            f"✅ Approved current job as text: {result.get('job_id')}\n\n"
            "🚀 Published to Facebook as a native text post.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )
    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Text approval or Facebook publish failed.\n\n{error}"
        )


async def retry_publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await asyncio.to_thread(control_retry_publish)

        await update.message.reply_text(
            f"🔁 Retried Facebook publish for job: {result.get('job_id')}\n\n"
            "🚀 Published to Facebook.\n\n"
            f"Post ID: {result.get('facebook_post_id')}"
        )

    except Exception as error:
        await update.message.reply_text(
            f"⚠️ Facebook publish failed.\n\n{error}"
        )


async def post_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = get_current_job()

    if not job:
        await update.message.reply_text("No current job.")
        return

    if not context.args:
        available = job.get("available_post_types") or ["image", "text"]
        lines = [
            "Current Post Type",
            "",
            f"Post Type: {job.get('post_type', 'image').upper()}",
            "Available: " + ", ".join(item.upper() for item in available),
        ]
        if job.get("suggested_post_type"):
            lines.append(
                "Suggested: "
                f"{job.get('suggested_post_type').upper()}"
            )
        if job.get("post_type", "image") == "text":
            lines.extend([
                "",
                "Facebook will publish the caption as a text-only post.",
            ])
        await send_job_preview(update, job, "\n".join(lines))
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Use /post_type_image or /post_type_text."
        )
        return

    await apply_post_type_intent(
        update,
        context.args[0],
        deprecated_alias=True,
    )


async def apply_post_type_intent(
    update: Update,
    post_type,
    deprecated_alias=False,
):
    try:
        result = await asyncio.to_thread(
            control_set_post_type,
            post_type,
        )
    except Exception as error:
        await update.message.reply_text(
            f"Post type was not changed.\n\n{error}"
        )
        return

    updated_job = result["job"]
    selected = result["post_type"].upper()
    notice = (
        "\n\nFacebook will publish the caption as a text-only post."
        if result["post_type"] == "text"
        else ""
    )
    deprecated_notice = (
        "\n\nThis syntax is deprecated.\n"
        f"Use: /post_type_{result['post_type']}"
        if deprecated_alias
        else ""
    )
    await send_job_preview(
        update,
        updated_job,
        f"Post Type: {selected}{notice}{deprecated_notice}",
    )


def post_type_intent_command(post_type):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await apply_post_type_intent(update, post_type)

    return handler


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
            f"Post Type: {job.get('post_type', 'image').upper()}",
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
    try:
        result = await asyncio.to_thread(control_reject_current_job)
    except Exception as error:
        await update.message.reply_text(f"⚠️ Reject failed.\n\n{error}")
        return

    await update.message.reply_text(
        f"❌ Job {result.get('job_id')} rejected and moved to history."
    )


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
    app.add_handler(CommandHandler("text_approve", admin_command(text_approve_command)))
    app.add_handler(CommandHandler("reject", admin_command(reject_command)))
    app.add_handler(CommandHandler("retry_publish", admin_command(retry_publish_command)))
    app.add_handler(CommandHandler("post_type", admin_command(post_type_command)))
    for command, post_type in POST_TYPE_INTENTS.items():
        app.add_handler(CommandHandler(
            command,
            admin_command(post_type_intent_command(post_type)),
        ))
    app.add_handler(CommandHandler("fbstatus", admin_command(fbstatus_command)))
    app.add_handler(CommandHandler("fb_reconnect", admin_command(fb_reconnect_command)))
    app.add_handler(CommandHandler("fb_set_token", admin_command(fb_set_token_command)))
    app.add_handler(CommandHandler("image_manual", admin_command(image_manual_command)))
    app.add_handler(CommandHandler("image_fit", admin_command(image_fit_command)))
    for command, mode in IMAGE_FIT_INTENTS.items():
        app.add_handler(CommandHandler(
            command,
            admin_command(image_fit_intent_command(mode)),
        ))
    app.add_handler(CommandHandler("image_status", admin_command(image_status_command)))
    app.add_handler(CommandHandler("image_show", admin_command(image_show_command)))
    app.add_handler(CommandHandler("image_builder", admin_command(image_builder_command)))
    app.add_handler(CommandHandler("image_validate", admin_command(image_validate_command)))
    app.add_handler(CommandHandler("image_reload", admin_command(image_reload_command)))
    app.add_handler(CommandHandler("image_upload", admin_command(image_upload_command)))
    app.add_handler(CommandHandler("scheduler_manual", admin_command(scheduler_manual_command)))
    app.add_handler(CommandHandler("scheduler_status", admin_command(scheduler_status_command)))
    app.add_handler(CommandHandler("scheduler_show", admin_command(scheduler_show_command)))
    app.add_handler(CommandHandler("scheduler_builder", admin_command(scheduler_builder_command)))
    app.add_handler(CommandHandler("scheduler_validate", admin_command(scheduler_validate_command)))
    app.add_handler(CommandHandler("scheduler_reload", admin_command(scheduler_reload_command)))
    app.add_handler(CommandHandler("scheduler_upload", admin_command(scheduler_upload_command)))
    app.add_handler(CommandHandler("language_manual", admin_command(language_manual_command)))
    app.add_handler(CommandHandler("language_status", admin_command(language_status_command)))
    app.add_handler(CommandHandler("language_show", admin_command(language_show_command)))
    app.add_handler(CommandHandler("language_builder", admin_command(language_builder_command)))
    app.add_handler(CommandHandler("language_validate", admin_command(language_validate_command)))
    app.add_handler(CommandHandler("language_reload", admin_command(language_reload_command)))
    app.add_handler(CommandHandler("language_upload", admin_command(language_upload_command)))
    app.add_handler(CommandHandler("windy_manual", admin_command(windy_manual_command)))
    app.add_handler(CommandHandler("windy_status", admin_command(windy_status_command)))
    app.add_handler(CommandHandler("windy_show", admin_command(windy_show_command)))
    app.add_handler(CommandHandler("windy_builder", admin_command(windy_builder_command)))
    app.add_handler(CommandHandler("windy_validate", admin_command(windy_validate_command)))
    app.add_handler(CommandHandler("windy_reload", admin_command(windy_reload_command)))
    app.add_handler(CommandHandler("windy_upload", admin_command(windy_upload_command)))
    app.add_handler(CommandHandler("windy_layer", admin_command(windy_layer_command)))
    for command, layer_id in WINDY_LAYER_INTENTS.items():
        app.add_handler(CommandHandler(
            command,
            admin_command(windy_layer_intent_command(layer_id)),
        ))
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
