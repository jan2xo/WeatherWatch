import copy
import json
import logging
from datetime import datetime
from pathlib import Path


LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path("config/post_types.json")
SUPPORTED_POST_TYPES = {"image", "text"}
DEFAULT_CONFIG = {
    "version": "1.0",
    "default_post_type": "image",
    "supported_post_types": ["image", "text"],
    "facebook": {
        "image": {
            "enabled": True,
            "description": "Publish final rendered image with caption.",
        },
        "text": {
            "enabled": True,
            "description": "Publish caption as a native Facebook text post.",
        },
        "video": {
            "enabled": False,
            "description": "Reserved for future video publishing.",
        },
    },
}

_config_cache = None
_last_loaded = None
_last_validation_error = None


def default_post_type_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def validate_post_type_config(config):
    if not isinstance(config, dict):
        raise ValueError("Post type configuration must be a JSON object.")

    for key in ("version", "default_post_type", "supported_post_types", "facebook"):
        if key not in config:
            raise ValueError(f"Missing required post type key: {key}")

    if not isinstance(config["version"], str) or not config["version"].strip():
        raise ValueError("version must be a non-empty string.")

    supported = config["supported_post_types"]
    if (
        not isinstance(supported, list)
        or not supported
        or any(item not in SUPPORTED_POST_TYPES for item in supported)
        or len(supported) != len(set(supported))
    ):
        raise ValueError(
            "supported_post_types may contain only unique image and text values."
        )

    default = config["default_post_type"]
    if default not in supported:
        raise ValueError("default_post_type must be supported.")

    facebook = config["facebook"]
    if not isinstance(facebook, dict):
        raise ValueError("facebook must be an object.")

    for post_type in supported:
        settings = facebook.get(post_type)
        if not isinstance(settings, dict):
            raise ValueError(f"Missing Facebook settings for: {post_type}")
        if not isinstance(settings.get("enabled"), bool):
            raise ValueError(f"facebook.{post_type}.enabled must be boolean.")
        if not isinstance(settings.get("description"), str):
            raise ValueError(
                f"facebook.{post_type}.description must be a string."
            )

    if not facebook[default]["enabled"]:
        raise ValueError("default_post_type must be enabled.")

    return True


def load_post_type_config_file(path=CONFIG_PATH):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_post_type_config(config)
    return config


def reload_post_type_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_post_type_config_file()
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return copy.deepcopy(_config_cache)


def get_post_type_config():
    global _config_cache, _last_loaded, _last_validation_error

    if _config_cache is not None:
        return copy.deepcopy(_config_cache)

    try:
        return reload_post_type_config()
    except Exception as error:
        LOGGER.warning(
            "Invalid post type configuration; using image-safe defaults: %s",
            error,
        )
        _last_validation_error = str(error)
        _config_cache = default_post_type_config()
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        return copy.deepcopy(_config_cache)


def get_enabled_post_types(config=None):
    active = config or get_post_type_config()
    return [
        post_type
        for post_type in active["supported_post_types"]
        if active["facebook"][post_type]["enabled"]
    ]


def validate_selected_post_type(post_type, config=None):
    active = config or get_post_type_config()
    normalized = str(post_type or "").strip().lower()

    if normalized not in active["supported_post_types"]:
        raise ValueError(f"Unsupported post type: {normalized or 'empty'}")
    if not active["facebook"][normalized]["enabled"]:
        raise ValueError(f"Post type is disabled: {normalized}")

    return normalized


def get_job_post_type_defaults():
    config = get_post_type_config()
    default = validate_selected_post_type(config["default_post_type"], config)
    return {
        "post_type": default,
        "available_post_types": get_enabled_post_types(config),
        "suggested_post_type": default,
        "post_type_reason": config["facebook"][default]["description"],
    }


def get_post_type_status():
    config = get_post_type_config()
    return {
        "config_path": str(CONFIG_PATH),
        "version": config.get("version"),
        "default_post_type": config.get("default_post_type"),
        "enabled_post_types": get_enabled_post_types(config),
        "last_loaded": _last_loaded,
        "validation_status": (
            "invalid" if _last_validation_error else "valid"
        ),
        "last_validation_error": _last_validation_error,
    }
