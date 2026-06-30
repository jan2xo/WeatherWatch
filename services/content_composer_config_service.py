import copy
import json
import logging
import string
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path("config/content_composer.json")
BACKUP_DIR = Path("data/composer_backups")
UPLOAD_DIR = Path("data/composer_uploads")
MAX_COMPOSER_UPLOAD_BYTES = 100 * 1024
MAX_COMPOSER_BACKUPS = 10
ALLOWED_PLACEHOLDERS = {
    "display_name",
    "areas_text",
    "subject",
    "parsed_forecast_text",
}
LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "version": "1.0",
    "language": "fil",
    "composer": {
        "default_source_line": "Forecast: PAGASA | pagasa.dost.gov.ph",
        "weather_systems": {
            "Southwest Monsoon": {
                "category": "monsoon",
                "display_name": "Habagat",
                "aliases": [
                    "Southwest Monsoon",
                    "Southwest Monsoon (Habagat)",
                    "Habagat",
                ],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang {display_name} o "
                    "Southwest Monsoon sa {areas_text}, ayon sa pinakahuling "
                    "weather bulletin ng PAGASA."
                ),
            },
            "Northeast Monsoon": {
                "category": "monsoon",
                "display_name": "Amihan",
                "aliases": [
                    "Northeast Monsoon",
                    "Northeast Monsoon (Amihan)",
                    "Amihan",
                ],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang {display_name} o "
                    "Northeast Monsoon sa {areas_text}, ayon sa pinakahuling "
                    "weather bulletin ng PAGASA."
                ),
            },
            "Intertropical Convergence Zone": {
                "category": "convergence_zone",
                "display_name": "ITCZ",
                "aliases": [
                    "Intertropical Convergence Zone",
                    "ITCZ",
                ],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang Intertropical Convergence "
                    "Zone o {display_name} sa {areas_text}, ayon sa "
                    "pinakahuling weather bulletin ng PAGASA."
                ),
            },
            "Low Pressure Area": {
                "category": "low_pressure_area",
                "display_name": "LPA",
                "aliases": ["Low Pressure Area", "LPA"],
                "headline_template": (
                    "{display_name} Binabantayan sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na binabantayan ang Low Pressure Area o "
                    "{display_name} na nakaaapekto sa {areas_text}, ayon sa "
                    "pinakahuling weather bulletin ng PAGASA."
                ),
            },
            "Easterlies": {
                "category": "wind_flow",
                "display_name": "Easterlies",
                "aliases": ["Easterlies"],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang Easterlies sa {areas_text}, "
                    "ayon sa pinakahuling weather bulletin ng PAGASA."
                ),
            },
            "Shear Line": {
                "category": "boundary",
                "display_name": "Shear Line",
                "aliases": ["Shear Line"],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang Shear Line sa {areas_text}, "
                    "ayon sa pinakahuling weather bulletin ng PAGASA."
                ),
            },
            "Frontal System": {
                "category": "boundary",
                "display_name": "Frontal System",
                "aliases": [
                    "Frontal System",
                    "Tail-end of a Frontal System",
                    "Tail-End of a Frontal System",
                ],
                "headline_template": (
                    "{display_name} Nakaaapekto sa {areas_text}"
                ),
                "summary_template": (
                    "Patuloy na nakaaapekto ang {display_name} sa "
                    "{areas_text}, ayon sa pinakahuling weather bulletin "
                    "ng PAGASA."
                ),
            },
        },
        "cyclone": {
            "headline_template": "{subject} Patuloy na Binabantayan",
            "fallback_headline": "Bagyo Patuloy na Binabantayan",
            "fallback_summary": (
                "Patuloy na binabantayan ng PAGASA ang bagyo."
            ),
        },
        "fallback": {
            "headline": "Weather Update",
            "primary_subject": "Weather Update",
            "summary": (
                "Patuloy na mino-monitor ang lagay ng panahon batay sa mga "
                "bulletin ng PAGASA."
            ),
        },
    },
}

_config_cache = None
_last_validation_error = None
_last_loaded = None


def default_composer_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def validate_string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")


def validate_template(value, path):
    validate_string(value, path)

    try:
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(value)
            if field_name
        }
    except ValueError as error:
        raise ValueError(f"{path} has invalid formatting: {error}") from error

    unknown = fields - ALLOWED_PLACEHOLDERS
    if unknown:
        raise ValueError(
            f"{path} has unknown placeholders: {', '.join(sorted(unknown))}"
        )


def normalize_alias(value):
    return " ".join(str(value or "").strip().casefold().split())


def normalize_composer_config(config, warn_legacy=False):
    normalized = copy.deepcopy(config)
    composer = (
        normalized.get("composer")
        if isinstance(normalized, dict)
        else None
    )
    if not isinstance(composer, dict):
        return normalized
    if "weather_systems" in composer:
        return normalized

    legacy_systems = (
        composer.get("monsoon", {}).get("systems")
        if isinstance(composer.get("monsoon"), dict)
        else None
    )
    if isinstance(legacy_systems, dict) and legacy_systems:
        composer["weather_systems"] = copy.deepcopy(legacy_systems)
        for system in composer["weather_systems"].values():
            if isinstance(system, dict):
                system.setdefault("category", "monsoon")
        if warn_legacy:
            LOGGER.warning(
                "Legacy composer.monsoon.systems config detected; "
                "using normalized composer.weather_systems."
            )

    return normalized


def validate_composer_config(config):
    if not isinstance(config, dict):
        raise ValueError("Composer config must be a JSON object")

    for key in ("version", "language", "composer"):
        if key not in config:
            raise ValueError(f"Missing required top-level key: {key}")

    validate_string(config["version"], "version")
    validate_string(config["language"], "language")

    normalized = normalize_composer_config(config)
    composer = normalized["composer"]
    if not isinstance(composer, dict):
        raise ValueError("composer must be an object")

    for key in (
        "default_source_line",
        "weather_systems",
        "cyclone",
        "fallback",
    ):
        if key not in composer:
            raise ValueError(f"Missing required composer key: {key}")

    validate_string(
        composer["default_source_line"],
        "composer.default_source_line",
    )

    systems = composer["weather_systems"]
    if not isinstance(systems, dict):
        raise ValueError("composer.weather_systems must be an object")
    if not systems:
        raise ValueError("composer.weather_systems must not be empty")

    aliases_seen = {}
    for system_name, system in systems.items():
        path = f"composer.weather_systems.{system_name}"
        validate_string(system_name, "weather system name")

        if not isinstance(system, dict):
            raise ValueError(f"{path} must be an object")

        for key in (
            "category",
            "display_name",
            "aliases",
            "headline_template",
            "summary_template",
        ):
            if key not in system:
                raise ValueError(f"Missing required key: {path}.{key}")

        validate_string(system["category"], f"{path}.category")
        validate_string(system["display_name"], f"{path}.display_name")
        aliases = system["aliases"]
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"{path}.aliases must be a non-empty array")
        for index, alias in enumerate(aliases):
            validate_string(alias, f"{path}.aliases[{index}]")
            normalized_alias = normalize_alias(alias)
            owner = aliases_seen.get(normalized_alias)
            if owner and owner != system_name:
                raise ValueError(
                    f"Duplicate weather-system alias {alias!r}: "
                    f"{owner} and {system_name}"
                )
            aliases_seen[normalized_alias] = system_name
        validate_template(
            system["headline_template"],
            f"{path}.headline_template",
        )
        validate_template(
            system["summary_template"],
            f"{path}.summary_template",
        )

    cyclone = composer["cyclone"]
    if not isinstance(cyclone, dict):
        raise ValueError("composer.cyclone must be an object")
    for key in (
        "headline_template",
        "fallback_headline",
        "fallback_summary",
    ):
        if key not in cyclone:
            raise ValueError(f"Missing required key: composer.cyclone.{key}")
    validate_template(
        cyclone["headline_template"],
        "composer.cyclone.headline_template",
    )
    validate_string(
        cyclone["fallback_headline"],
        "composer.cyclone.fallback_headline",
    )
    validate_string(
        cyclone["fallback_summary"],
        "composer.cyclone.fallback_summary",
    )

    fallback = composer["fallback"]
    if not isinstance(fallback, dict):
        raise ValueError("composer.fallback must be an object")
    for key in ("headline", "primary_subject", "summary"):
        if key not in fallback:
            raise ValueError(f"Missing required key: composer.fallback.{key}")
        validate_template(fallback[key], f"composer.fallback.{key}")

    return True


def validate_composer_upload_size(path):
    if Path(path).stat().st_size > MAX_COMPOSER_UPLOAD_BYTES:
        raise ValueError("Composer upload rejected: file too large.")


def load_composer_config_file(path=None):
    config_path = Path(path or CONFIG_PATH)
    validate_composer_upload_size(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_composer_config(config)
    return normalize_composer_config(config, warn_legacy=True)


def reload_composer_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_composer_config_file(CONFIG_PATH)
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return _config_cache


def get_composer_config():
    global _config_cache, _last_loaded, _last_validation_error

    if _config_cache is not None:
        return _config_cache

    try:
        return reload_composer_config()
    except Exception as error:
        _last_validation_error = str(error)
        _config_cache = default_composer_config()
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        return _config_cache


def save_composer_config(config, path=None):
    validate_composer_config(config)
    config_path = Path(path or CONFIG_PATH)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)
    return config


def utc_timestamp():
    return datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")


def backup_current_composer_config():
    if not CONFIG_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"content_composer.{utc_timestamp()}.json"
    backup_path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    prune_composer_backups()
    return backup_path


def prune_composer_backups(max_backups=MAX_COMPOSER_BACKUPS):
    if not BACKUP_DIR.exists():
        return []

    backups = sorted(
        BACKUP_DIR.glob("content_composer.*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = []

    for backup in backups[max_backups:]:
        backup.unlink()
        removed.append(str(backup))

    return removed


def replace_composer_config_from_file(uploaded_path):
    config = load_composer_config_file(uploaded_path)
    backup_current_composer_config()
    save_composer_config(config, CONFIG_PATH)
    reload_composer_config()
    return get_composer_status()


def get_composer_status():
    try:
        config = load_composer_config_file(CONFIG_PATH)
        validation_status = "valid"
        validation_error = None
    except Exception as error:
        config = _config_cache or default_composer_config()
        validation_status = "invalid"
        validation_error = str(error)

    return {
        "config_path": str(CONFIG_PATH),
        "version": config.get("version"),
        "language": config.get("language"),
        "last_loaded": _last_loaded,
        "validation_status": validation_status,
        "last_validation_error": (
            validation_error or _last_validation_error
        ),
        "weather_system_count": len(
            config.get("composer", {}).get("weather_systems", {})
        ),
        "weather_systems": [
            {
                "name": name,
                "category": settings.get("category"),
                "display_name": settings.get("display_name"),
            }
            for name, settings in (
                config.get("composer", {})
                .get("weather_systems", {})
                .items()
            )
        ],
    }


def composer_json_preview(limit=3500):
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("Composer configuration does not exist.")

    text = CONFIG_PATH.read_text(encoding="utf-8")
    if len(text) <= limit:
        return text

    return text[:limit] + "\n\n... shortened preview ..."


def starter_composer_json():
    return json.dumps(
        default_composer_config(),
        indent=2,
        ensure_ascii=False,
    )
