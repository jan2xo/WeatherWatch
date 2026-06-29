import copy
import json
import logging
from datetime import datetime
from pathlib import Path


LOGGER = logging.getLogger(__name__)

CONFIG_PATH = Path("config/language_normalization.json")
BACKUP_DIR = Path("data/language_backups")
UPLOAD_DIR = Path("data/language_uploads")
MAX_LANGUAGE_UPLOAD_BYTES = 100 * 1024
MAX_LANGUAGE_BACKUPS = 10
SUPPORTED_FORMS = {"body", "headline", "short"}
REQUIRED_DIRECTIONS = (
    "western",
    "eastern",
    "northern",
    "southern",
    "central",
)
REQUIRED_REGIONS = (
    "the Philippines",
    "Luzon",
    "Visayas",
    "Mindanao",
    "Northern Luzon",
    "Central Luzon",
    "Southern Luzon",
    "Western Luzon",
    "Eastern Luzon",
    "Northern Visayas",
    "Central Visayas",
    "Western Visayas",
    "Eastern Visayas",
    "Northern Mindanao",
    "Southern Mindanao",
    "Western Mindanao",
    "Eastern Mindanao",
    "Central Mindanao",
)

_config_cache = None
_last_loaded = None
_last_validation_error = None


def default_language_config():
    return {
        "version": "1.0",
        "language": "fil",
        "area_phrases": {},
    }


def normalize_lookup_key(value):
    return " ".join(str(value or "").strip().casefold().split())


def required_area_phrases():
    return {
        f"the {direction} section of {region}"
        for region in REQUIRED_REGIONS
        for direction in REQUIRED_DIRECTIONS
    }


def validate_language_config(config):
    if not isinstance(config, dict):
        raise ValueError(
            "Language normalization configuration must be a JSON object."
        )

    for key in ("version", "language", "area_phrases"):
        if key not in config:
            raise ValueError(f"Missing required language key: {key}")

    if not isinstance(config["version"], str) or not config["version"].strip():
        raise ValueError("version must be a non-empty string.")
    if not isinstance(config["language"], str) or not config["language"].strip():
        raise ValueError("language must be a non-empty string.")

    phrases = config["area_phrases"]
    if not isinstance(phrases, dict):
        raise ValueError("area_phrases must be an object.")

    normalized_entries = {}
    for phrase, forms in phrases.items():
        normalized_phrase = normalize_lookup_key(phrase)
        if not normalized_phrase:
            raise ValueError("Area phrase keys must not be empty.")
        if normalized_phrase in normalized_entries:
            raise ValueError(f"Duplicate normalized area phrase: {phrase}")
        if not isinstance(forms, dict):
            raise ValueError(f"Area phrase {phrase!r} must be an object.")

        for form in SUPPORTED_FORMS:
            value = forms.get(form)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Area phrase {phrase!r} requires {form}."
                )

        normalized_entries[normalized_phrase] = forms

    missing = [
        phrase
        for phrase in sorted(required_area_phrases())
        if normalize_lookup_key(phrase) not in normalized_entries
    ]
    if missing:
        raise ValueError(
            "Missing required area phrases: " + ", ".join(missing)
        )

    return True


def validate_language_upload_size(path):
    if Path(path).stat().st_size > MAX_LANGUAGE_UPLOAD_BYTES:
        raise ValueError("Language upload rejected: file too large.")


def load_language_config_file(path=CONFIG_PATH):
    config_path = Path(path)
    validate_language_upload_size(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_language_config(config)
    return config


def reload_language_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_language_config_file(CONFIG_PATH)
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return copy.deepcopy(_config_cache)


def get_language_config():
    global _config_cache, _last_loaded, _last_validation_error

    if _config_cache is not None:
        return copy.deepcopy(_config_cache)

    try:
        return reload_language_config()
    except Exception as error:
        LOGGER.warning(
            "Language normalization config unavailable; preserving source text: %s",
            error,
        )
        _last_validation_error = str(error)
        _config_cache = default_language_config()
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        return copy.deepcopy(_config_cache)


def save_language_config(config, path=CONFIG_PATH):
    validate_language_config(config)
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)
    return copy.deepcopy(config)


def normalize_area_phrase(text, form="body", config=None):
    if form not in SUPPORTED_FORMS:
        raise ValueError(f"Unsupported normalization form: {form}")
    if not isinstance(text, str) or not text:
        return text

    active_config = config or get_language_config()
    lookup = {
        normalize_lookup_key(phrase): forms
        for phrase, forms in active_config.get("area_phrases", {}).items()
    }
    match = lookup.get(normalize_lookup_key(text))
    if not match:
        return text

    return match[form]


def normalize_area_list(areas, form="body", config=None):
    return [
        normalize_area_phrase(area, form=form, config=config)
        for area in (areas or [])
    ]


def normalize_forecast_data(forecast_data):
    normalized = copy.deepcopy(
        forecast_data if isinstance(forecast_data, dict) else {}
    )
    areas = normalized.get("affected_areas") or []
    config = get_language_config()
    normalized["affected_areas_original"] = list(areas)
    normalized["affected_areas"] = normalize_area_list(
        areas,
        form="body",
        config=config,
    )
    normalized["affected_areas_headline"] = normalize_area_list(
        areas,
        form="headline",
        config=config,
    )
    normalized["affected_areas_short"] = normalize_area_list(
        areas,
        form="short",
        config=config,
    )
    return normalized


def backup_current_language_config():
    if not CONFIG_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    backup_path = BACKUP_DIR / f"language_normalization.{timestamp}.json"
    backup_path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    backups = sorted(
        BACKUP_DIR.glob("language_normalization.*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_LANGUAGE_BACKUPS:]:
        old_backup.unlink()
    return backup_path


def replace_language_config_from_file(uploaded_path):
    config = load_language_config_file(uploaded_path)
    backup_current_language_config()
    save_language_config(config, CONFIG_PATH)
    reload_language_config()
    return get_language_status()


def get_language_status():
    try:
        config = load_language_config_file(CONFIG_PATH)
        validation_status = "valid"
        validation_error = None
    except Exception as error:
        config = _config_cache or default_language_config()
        validation_status = "invalid"
        validation_error = str(error)

    return {
        "config_path": str(CONFIG_PATH),
        "version": config.get("version"),
        "language": config.get("language"),
        "phrase_count": len(config.get("area_phrases", {})),
        "validation_status": validation_status,
        "last_loaded": _last_loaded,
        "last_validation_error": (
            validation_error or _last_validation_error
        ),
    }


def language_json_preview(limit=3500):
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "Language normalization configuration does not exist."
        )
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n\n... shortened preview ..."


def starter_language_json():
    config = get_language_config()
    return json.dumps(config, indent=2, ensure_ascii=False)
