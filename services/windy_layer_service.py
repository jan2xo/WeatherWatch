import copy
import json
import logging
import math
import string
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


LOGGER = logging.getLogger(__name__)
CONFIG_PATH = Path("config/windy_layers.json")
BACKUP_DIR = Path("data/windy_backups")
UPLOAD_DIR = Path("data/windy_uploads")
MAX_WINDY_UPLOAD_BYTES = 100 * 1024
MAX_WINDY_BACKUPS = 10
REQUIRED_URL_FIELDS = {"lat", "lon", "zoom"}
SAFE_SATELLITE_PATTERN = (
    "https://www.windy.com/-Satellite-satellite"
    "?satellite,{lat},{lon},{zoom}"
)
DEFAULT_CONFIG = {
    "version": "1.0",
    "default_layer": "satellite",
    "rotation_enabled": False,
    "layers": {
        "satellite": {
            "enabled": True,
            "label": "Satellite",
            "url_pattern": SAFE_SATELLITE_PATTERN,
            "description": "Best general-purpose weather situation layer.",
        },
    },
    "suggestion_rules": {
        "default": "satellite",
        "monsoon": "satellite",
        "cyclone": "satellite",
        "lpa": "satellite",
    },
}

_config_cache = None
_last_loaded = None
_last_validation_error = None


def default_windy_layer_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def _template_fields(pattern):
    try:
        return {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(pattern)
            if field_name
        }
    except ValueError as error:
        raise ValueError("Windy URL pattern is malformed.") from error


def validate_windy_layer_config(config):
    if not isinstance(config, dict):
        raise ValueError("Windy layer configuration must be a JSON object.")

    for key in (
        "version",
        "default_layer",
        "rotation_enabled",
        "layers",
        "suggestion_rules",
    ):
        if key not in config:
            raise ValueError(f"Missing required Windy key: {key}")

    if not isinstance(config["version"], str) or not config["version"].strip():
        raise ValueError("version must be a non-empty string.")
    if not isinstance(config["rotation_enabled"], bool):
        raise ValueError("rotation_enabled must be true or false.")

    layers = config["layers"]
    if not isinstance(layers, dict) or not layers:
        raise ValueError("layers must be a non-empty object.")

    for layer_id, layer in layers.items():
        if not isinstance(layer_id, str) or not layer_id.strip():
            raise ValueError("Windy layer IDs must be non-empty strings.")
        if not isinstance(layer, dict):
            raise ValueError(f"Layer {layer_id!r} must be an object.")
        if not isinstance(layer.get("enabled"), bool):
            raise ValueError(f"layers.{layer_id}.enabled must be boolean.")
        if not isinstance(layer.get("label"), str) or not layer["label"].strip():
            raise ValueError(f"layers.{layer_id}.label is required.")

        pattern = layer.get("url_pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"layers.{layer_id}.url_pattern is required.")
        fields = _template_fields(pattern)
        if fields != REQUIRED_URL_FIELDS:
            raise ValueError(
                f"layers.{layer_id}.url_pattern must contain only "
                "{lat}, {lon}, and {zoom}."
            )
        parsed_url = urlsplit(pattern)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in {"windy.com", "www.windy.com"}
        ):
            raise ValueError(
                f"layers.{layer_id}.url_pattern must use HTTPS windy.com."
            )

    default_layer = config["default_layer"]
    if default_layer not in layers:
        raise ValueError("default_layer is unknown.")
    if not layers[default_layer]["enabled"]:
        raise ValueError("default_layer must be enabled.")
    if "satellite" not in layers or not layers["satellite"]["enabled"]:
        raise ValueError("The satellite fallback layer must be enabled.")

    rules = config["suggestion_rules"]
    if not isinstance(rules, dict) or "default" not in rules:
        raise ValueError("suggestion_rules must include default.")
    for situation, layer_id in rules.items():
        if not isinstance(situation, str) or not situation.strip():
            raise ValueError("Suggestion rule names must not be empty.")
        if layer_id not in layers:
            raise ValueError(
                f"Suggestion rule {situation!r} uses unknown layer {layer_id!r}."
            )
        if not layers[layer_id]["enabled"]:
            raise ValueError(
                f"Suggestion rule {situation!r} uses disabled layer {layer_id!r}."
            )

    return True


def validate_windy_upload_size(path):
    if Path(path).stat().st_size > MAX_WINDY_UPLOAD_BYTES:
        raise ValueError("Windy upload rejected: file too large.")


def load_windy_layer_config_file(path=CONFIG_PATH):
    config_path = Path(path)
    validate_windy_upload_size(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_windy_layer_config(config)
    return config


def reload_windy_layer_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_windy_layer_config_file()
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return copy.deepcopy(_config_cache)


def get_windy_layer_config():
    global _config_cache, _last_loaded, _last_validation_error

    if _config_cache is not None:
        return copy.deepcopy(_config_cache)

    try:
        return reload_windy_layer_config()
    except Exception as error:
        LOGGER.warning(
            "Windy layer config unavailable; using satellite fallback: %s",
            error,
        )
        _last_validation_error = str(error)
        _config_cache = default_windy_layer_config()
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        return copy.deepcopy(_config_cache)


def save_windy_layer_config(config, path=CONFIG_PATH):
    validate_windy_layer_config(config)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return copy.deepcopy(config)


def get_enabled_layers(config=None):
    active = config or get_windy_layer_config()
    return [
        {
            "id": layer_id,
            "label": layer["label"],
        }
        for layer_id, layer in active["layers"].items()
        if layer["enabled"]
    ]


def get_default_layer():
    return get_windy_layer_config()["default_layer"]


def set_default_layer(layer_id):
    config = get_windy_layer_config()
    selected, _ = get_layer(layer_id, config)
    config["default_layer"] = selected
    save_windy_layer_config(config)
    reload_windy_layer_config()
    return selected


def get_layer(layer_id, config=None):
    active = config or get_windy_layer_config()
    normalized = str(layer_id or "").strip().lower()
    layer = active["layers"].get(normalized)
    if not layer:
        raise ValueError(f"Unknown Windy layer: {normalized or 'empty'}")
    if not layer["enabled"]:
        raise ValueError(f"Windy layer is disabled: {normalized}")
    return normalized, layer


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Windy {label} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Windy {label} must be finite.")
    return number


def build_windy_url(layer_id, lat, lon, zoom):
    normalized, layer = get_layer(layer_id)
    latitude = _number(lat, "latitude")
    longitude = _number(lon, "longitude")
    zoom_value = _number(zoom, "zoom")

    if not -90 <= latitude <= 90:
        raise ValueError("Windy latitude is outside the valid range.")
    if not -180 <= longitude <= 180:
        raise ValueError("Windy longitude is outside the valid range.")
    if zoom_value <= 0:
        raise ValueError("Windy zoom must be greater than zero.")

    zoom_text = (
        str(int(zoom_value))
        if zoom_value.is_integer()
        else str(zoom_value)
    )
    return layer["url_pattern"].format(
        lat=f"{latitude:.3f}",
        lon=f"{longitude:.3f}",
        zoom=zoom_text,
    )


def _suggestion_situation(forecast_data, parsed_forecast_text):
    data = forecast_data if isinstance(forecast_data, dict) else {}
    text = " ".join([
        str(parsed_forecast_text or ""),
        str(data.get("affected_weather_system") or ""),
        str(data.get("weather_type") or ""),
    ]).casefold()

    if data.get("cyclone_classification") or data.get("cyclone_name_local"):
        return "cyclone"
    if "low pressure area" in text or " lpa " in f" {text} ":
        return "lpa"
    if "southwest monsoon" in text or "northeast monsoon" in text:
        return "monsoon"
    if "thunderstorm" in text:
        return "thunderstorm"
    if "heavy rain" in text:
        return "heavy_rain"
    if "wind advisory" in text or "strong winds" in text:
        return "wind_advisory"
    if "temperature" in text or "heat index" in text:
        return "temperature"
    return "default"


def suggest_windy_layer(forecast_data, parsed_forecast_text=None):
    config = get_windy_layer_config()
    situation = _suggestion_situation(
        forecast_data,
        parsed_forecast_text,
    )
    selected = config["suggestion_rules"].get(
        situation,
        config["suggestion_rules"]["default"],
    )
    return get_layer(selected, config)[0]


def framing_coordinates(framing_decision):
    decision = (
        framing_decision
        if isinstance(framing_decision, dict)
        else {}
    )
    latitude = _number(decision.get("center_lat"), "latitude")
    longitude = _number(decision.get("center_lon"), "longitude")
    zoom = _number(decision.get("zoom"), "zoom")
    pan_x = _number(decision.get("pan_x", 0), "horizontal pan")
    pan_y = _number(decision.get("pan_y", 0), "vertical pan")
    return latitude + pan_y, longitude + pan_x, zoom


def build_windy_job_metadata(
    framing_decision,
    forecast_data=None,
    parsed_forecast_text=None,
    layer_id=None,
):
    config = get_windy_layer_config()
    selected = layer_id or config["default_layer"]
    selected, layer = get_layer(selected, config)
    suggested = suggest_windy_layer(
        forecast_data,
        parsed_forecast_text,
    )
    latitude, longitude, zoom = framing_coordinates(framing_decision)
    return {
        "windy_layer": selected,
        "windy_layer_label": layer["label"],
        "suggested_windy_layer": suggested,
        "windy_url": build_windy_url(
            selected,
            latitude,
            longitude,
            zoom,
        ),
    }


def backup_current_windy_config():
    if not CONFIG_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    backup_path = BACKUP_DIR / f"windy_layers.{timestamp}.json"
    backup_path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    backups = sorted(
        BACKUP_DIR.glob("windy_layers.*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_WINDY_BACKUPS:]:
        old_backup.unlink()
    return backup_path


def replace_windy_config_from_file(uploaded_path):
    config = load_windy_layer_config_file(uploaded_path)
    backup_current_windy_config()
    save_windy_layer_config(config)
    reload_windy_layer_config()
    return get_windy_layer_status()


def get_windy_layer_status():
    try:
        config = load_windy_layer_config_file()
        validation_status = "valid"
        validation_error = None
    except Exception as error:
        config = _config_cache or default_windy_layer_config()
        validation_status = "invalid"
        validation_error = str(error)

    enabled = get_enabled_layers(config)
    disabled = [
        {"id": layer_id, "label": layer["label"]}
        for layer_id, layer in config.get("layers", {}).items()
        if not layer["enabled"]
    ]
    return {
        "config_path": str(CONFIG_PATH),
        "version": config.get("version"),
        "validation_status": validation_status,
        "last_loaded": _last_loaded,
        "last_validation_error": validation_error or _last_validation_error,
        "default_layer": config.get("default_layer"),
        "rotation_enabled": config.get("rotation_enabled", False),
        "enabled_layers": enabled,
        "disabled_layers": disabled,
    }


def windy_json_preview(limit=3500):
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("Windy layer configuration does not exist.")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n\n... shortened preview ..."


def starter_windy_json():
    return json.dumps(get_windy_layer_config(), indent=2)
