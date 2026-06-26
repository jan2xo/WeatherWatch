import json
import string
from datetime import datetime
from pathlib import Path


TEMPLATE_PATH = Path("config/caption_templates.pagasa.json")
BACKUP_DIR = Path("data/template_backups")
REQUIRED_TOP_LEVEL_KEYS = {
    "version",
    "language",
    "provider",
    "templates",
    "translations",
}
REQUIRED_TEMPLATE_KEYS = {
    "cyclone_location",
    "cyclone_intensity",
    "cyclone_movement",
    "affected_system",
    "source_line",
}
REQUIRED_TRANSLATION_KEYS = {
    "weather_systems",
    "movement_directions",
}
ALLOWED_TEMPLATE_FIELDS = {
    "classification",
    "hashtag",
    "international_name",
    "location_text",
    "maximum_sustained_winds_kmh",
    "gustiness_kmh",
    "movement_direction",
    "movement_speed_kmh",
    "weather_system",
    "affected_areas",
}

_template_cache = None
_last_validation_error = None


class SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def utc_timestamp():
    return datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")


def load_json_file(path):
    return json.loads(Path(path).read_text())


def validate_template_structure(template):
    missing = REQUIRED_TOP_LEVEL_KEYS - set(template)

    if missing:
        raise ValueError(f"Missing required top-level keys: {', '.join(sorted(missing))}")

    templates = template.get("templates")
    translations = template.get("translations")

    if not isinstance(templates, dict):
        raise ValueError("templates must be an object")

    if not isinstance(translations, dict):
        raise ValueError("translations must be an object")

    missing_templates = REQUIRED_TEMPLATE_KEYS - set(templates)
    if missing_templates:
        raise ValueError(f"Missing required templates: {', '.join(sorted(missing_templates))}")

    missing_translations = REQUIRED_TRANSLATION_KEYS - set(translations)
    if missing_translations:
        raise ValueError(f"Missing required translations: {', '.join(sorted(missing_translations))}")

    for key in REQUIRED_TEMPLATE_KEYS:
        if not isinstance(templates.get(key), str):
            raise ValueError(f"templates.{key} must be a string")

        field_names = [
            field_name
            for _, field_name, _, _ in string.Formatter().parse(templates[key])
            if field_name
        ]
        unknown_fields = set(field_names) - ALLOWED_TEMPLATE_FIELDS

        if unknown_fields:
            raise ValueError(
                f"templates.{key} has unknown placeholders: {', '.join(sorted(unknown_fields))}"
            )

    for key in REQUIRED_TRANSLATION_KEYS:
        if not isinstance(translations.get(key), dict):
            raise ValueError(f"translations.{key} must be an object")

    return True


def validate_template_file(path=TEMPLATE_PATH):
    template = load_json_file(path)
    validate_template_structure(template)
    return template


def reload_templates():
    global _template_cache
    global _last_validation_error

    try:
        template = validate_template_file(TEMPLATE_PATH)
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _template_cache = template
    _last_validation_error = None
    return template


def get_template():
    global _template_cache

    if _template_cache is None:
        return reload_templates()

    return _template_cache


def get_template_status():
    try:
        template = validate_template_file(TEMPLATE_PATH)
        validation_status = "valid"
        validation_error = None
    except Exception as error:
        template = _template_cache or {}
        validation_status = "invalid"
        validation_error = str(error)

    modified = None
    if TEMPLATE_PATH.exists():
        modified = datetime.fromtimestamp(TEMPLATE_PATH.stat().st_mtime).isoformat(timespec="seconds")

    return {
        "provider": template.get("provider"),
        "version": template.get("version"),
        "language": template.get("language"),
        "last_modified": modified,
        "validation_status": validation_status,
        "last_validation_error": validation_error or _last_validation_error,
    }


def template_json_preview(limit=3500):
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError("Caption template file does not exist.")

    text = TEMPLATE_PATH.read_text()

    if len(text) <= limit:
        return text

    return text[:limit] + "\n\n... shortened preview ..."


def starter_template_json():
    template = get_template()
    return json.dumps(template, indent=2, ensure_ascii=False)


def backup_current_template():
    if not TEMPLATE_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"caption_templates.pagasa.{utc_timestamp()}.json"
    backup_path.write_text(TEMPLATE_PATH.read_text())
    return backup_path


def replace_template_from_file(uploaded_path):
    template = validate_template_file(uploaded_path)
    backup_current_template()
    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_text(json.dumps(template, indent=2, ensure_ascii=False))
    reload_templates()
    return get_template_status()


def translate(category, value):
    if not value:
        return ""

    translations = get_template().get("translations", {}).get(category, {})
    return translations.get(value.lower(), value)


def render_template(template_name, values):
    template = get_template()["templates"][template_name]
    return template.format_map(SafeFormatDict(values)).strip()
