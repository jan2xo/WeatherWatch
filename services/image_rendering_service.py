import json
import logging
from pathlib import Path

from PIL import Image, ImageOps


LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "image_rendering.json"
TARGET_SIZE = (1080, 1350)
DEFAULT_FIT_MODE = "smartfit"
SUPPORTED_FIT_MODES = ("stretch", "smartfit", "crop")


def default_config():
    return {
        "fit_mode": DEFAULT_FIT_MODE,
        "target_width": TARGET_SIZE[0],
        "target_height": TARGET_SIZE[1],
    }


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Image rendering configuration must be a JSON object.")

    mode = config.get("fit_mode")
    if mode not in SUPPORTED_FIT_MODES:
        raise ValueError(f"Unsupported image fit mode: {mode!r}.")

    size = (config.get("target_width"), config.get("target_height"))
    if size != TARGET_SIZE:
        raise ValueError("Image rendering canvas must be 1080x1350.")

    return {
        "fit_mode": mode,
        "target_width": TARGET_SIZE[0],
        "target_height": TARGET_SIZE[1],
    }


def load_config(config_path=CONFIG_PATH):
    path = Path(config_path)

    if not path.exists():
        return default_config()

    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        LOGGER.warning(
            "Invalid image rendering configuration; using smartfit: %s",
            error,
        )
        return default_config()


def save_config(config, config_path=CONFIG_PATH):
    validated = validate_config(config)
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(validated, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return validated


def set_fit_mode(mode, config_path=CONFIG_PATH):
    normalized_mode = (mode or "").strip().lower()

    if normalized_mode not in SUPPORTED_FIT_MODES:
        raise ValueError(
            "Unsupported mode. Use stretch, smartfit, or crop."
        )

    config = default_config()
    config["fit_mode"] = normalized_mode
    return save_config(config, config_path=config_path)


def get_image_rendering_status(config_path=CONFIG_PATH):
    config = load_config(config_path=config_path)
    return {
        **config,
        "available_modes": SUPPORTED_FIT_MODES,
    }


def stretch(image, target_size=TARGET_SIZE):
    return image.resize(target_size, Image.Resampling.LANCZOS)


def smartfit(image, target_size=TARGET_SIZE):
    return ImageOps.fit(
        image,
        target_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def crop(image, target_size=TARGET_SIZE):
    target_width, target_height = target_size
    source_width, source_height = image.size

    if source_width < target_width or source_height < target_height:
        return smartfit(image, target_size)

    left = (source_width - target_width) // 2
    top = (source_height - target_height) // 2
    return image.crop((
        left,
        top,
        left + target_width,
        top + target_height,
    ))


def apply_image_fit(image, config_path=CONFIG_PATH):
    config = load_config(config_path=config_path)
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    mode = config["fit_mode"]

    try:
        if mode == "stretch":
            return stretch(prepared)
        if mode == "crop":
            return crop(prepared)
        return smartfit(prepared)
    except Exception as error:
        LOGGER.warning(
            "Image rendering failed in %s mode; using smartfit: %s",
            mode,
            error,
        )
        return smartfit(prepared)


def render_manual_image(input_path, output_path=None, config_path=CONFIG_PATH):
    source_path = Path(input_path)
    destination_path = Path(output_path) if output_path else source_path

    with Image.open(source_path) as image:
        rendered = apply_image_fit(image, config_path=config_path)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(destination_path, format="JPEG", quality=95)
    return str(destination_path)
