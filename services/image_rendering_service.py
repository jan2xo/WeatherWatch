import copy
import json
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps


LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "image_rendering.json"
BACKUP_DIR = BASE_DIR / "data" / "image_rendering_backups"
UPLOAD_DIR = BASE_DIR / "data" / "image_rendering_uploads"
TARGET_SIZE = (1080, 1350)
DEFAULT_FIT_MODE = "smartfit"
SUPPORTED_FIT_MODES = ("stretch", "smartfit", "crop")
SUPPORTED_FRAMING_STRATEGIES = ("region", "weather_system")
PARENT_REGION_GROUPS = ("philippines", "luzon", "visayas", "mindanao")
REQUIRED_BROAD_REGIONS = (
    "philippines",
    "luzon",
    "visayas",
    "mindanao",
    "luzon_visayas",
    "visayas_mindanao",
)
REQUIRED_SUBREGIONS = (
    "northern_luzon",
    "central_luzon",
    "southern_luzon",
    "western_luzon",
    "eastern_luzon",
    "northern_visayas",
    "central_visayas",
    "southern_visayas",
    "western_visayas",
    "eastern_visayas",
    "northern_mindanao",
    "central_mindanao",
    "southern_mindanao",
    "western_mindanao",
    "eastern_mindanao",
)
MAX_IMAGE_RENDERING_UPLOAD_BYTES = 100 * 1024
MAX_IMAGE_RENDERING_BACKUPS = 10

_config_cache = None
_last_loaded = None
_last_validation_error = None


def default_config():
    return {
        "version": "1.0",
        "manual_image": {
            "fit_mode": DEFAULT_FIT_MODE,
            "target_width": TARGET_SIZE[0],
            "target_height": TARGET_SIZE[1],
        },
        "auto_map": {
            "enabled": True,
            "target_width": TARGET_SIZE[0],
            "target_height": TARGET_SIZE[1],
            "framing": {
                "enabled": True,
                "default": {
                    "strategy": "region",
                    "region_id": "philippines",
                    "zoom": 5,
                    "pan_x": 0,
                    "pan_y": 0,
                    "reason": "Default Philippines framing",
                },
                "regions": {
                    "philippines": {
                        "parent_group": "philippines",
                        "aliases": [
                            "Philippines",
                            "the Philippines",
                            "Pilipinas",
                        ],
                        "center_lat": 12.8797,
                        "center_lon": 121.7740,
                        "zoom": 5,
                    },
                    "luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Luzon"],
                        "center_lat": 16.0,
                        "center_lon": 121.0,
                        "zoom": 6,
                    },
                    "visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Visayas"],
                        "center_lat": 10.5,
                        "center_lon": 123.5,
                        "zoom": 6,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "luzon_visayas": {
                        "parent_group": "philippines",
                        "aliases": ["Luzon and Visayas", "Luzon at Visayas"],
                        "center_lat": 13.5,
                        "center_lon": 122.5,
                        "zoom": 5,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Mindanao"],
                        "center_lat": 7.8,
                        "center_lon": 125.0,
                        "zoom": 6,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "visayas_mindanao": {
                        "parent_group": "philippines",
                        "aliases": [
                            "Visayas and Mindanao",
                            "Visayas at Mindanao",
                        ],
                        "center_lat": 8.9,
                        "center_lon": 124.3,
                        "zoom": 5,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "northern_luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Northern Luzon", "Hilagang Luzon"],
                        "center_lat": 17.5,
                        "center_lon": 121.5,
                        "zoom": 6,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "southern_luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Southern Luzon", "Timog Luzon"],
                        "center_lat": 13.5,
                        "center_lon": 121.3,
                        "zoom": 6,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "central_luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Central Luzon", "Gitnang Luzon"],
                        "center_lat": 15.3,
                        "center_lon": 120.8,
                        "zoom": 7,
                        "pan_x": 0,
                        "pan_y": 0,
                    },
                    "western_luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Western Luzon", "Kanlurang Luzon"],
                    },
                    "eastern_luzon": {
                        "parent_group": "luzon",
                        "aliases": ["Eastern Luzon", "Silangang Luzon"],
                    },
                    "northern_visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Northern Visayas", "Hilagang Visayas"],
                    },
                    "central_visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Central Visayas", "Gitnang Visayas"],
                    },
                    "southern_visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Southern Visayas", "Timog Visayas"],
                    },
                    "western_visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Western Visayas", "Kanlurang Visayas"],
                    },
                    "eastern_visayas": {
                        "parent_group": "visayas",
                        "aliases": ["Eastern Visayas", "Silangang Visayas"],
                    },
                    "northern_mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Northern Mindanao", "Hilagang Mindanao"],
                    },
                    "central_mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Central Mindanao", "Gitnang Mindanao"],
                    },
                    "southern_mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Southern Mindanao", "Timog Mindanao"],
                    },
                    "western_mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Western Mindanao", "Kanlurang Mindanao"],
                    },
                    "eastern_mindanao": {
                        "parent_group": "mindanao",
                        "aliases": ["Eastern Mindanao", "Silangang Mindanao"],
                    },
                },
                "area_routing": {
                    "enabled": True,
                    "parent_group_combinations": {
                        "luzon+visayas": "luzon_visayas",
                        "visayas+mindanao": "visayas_mindanao",
                        "luzon+mindanao": "philippines",
                        "luzon+visayas+mindanao": "philippines",
                    },
                },
                "situations": {
                    "monsoon_southwest": {
                        "aliases": [
                            "Southwest Monsoon",
                            "Habagat",
                            "Southwest Monsoon (Habagat)",
                        ],
                        "strategy": "region",
                        "region_id": "luzon_visayas",
                        "zoom": 5,
                        "pan_x": 0,
                        "pan_y": 0,
                        "reason": "Habagat affecting Luzon and Visayas",
                    },
                    "monsoon_northeast": {
                        "aliases": [
                            "Northeast Monsoon",
                            "Amihan",
                            "Northeast Monsoon (Amihan)",
                        ],
                        "strategy": "region",
                        "region_id": "northern_luzon",
                        "zoom": 6,
                        "pan_x": 0,
                        "pan_y": 0,
                        "reason": "Amihan affecting Northern Luzon",
                    },
                    "lpa": {
                        "aliases": ["Low Pressure Area", "LPA"],
                        "strategy": "weather_system",
                        "zoom": 5,
                        "include_nearest_landmass": True,
                        "pan_x": 0,
                        "pan_y": 0,
                        "reason": "LPA detected",
                    },
                    "cyclone": {
                        "strategy": "weather_system",
                        "zoom": 5,
                        "pan_x": 0,
                        "pan_y": 0,
                        "reason": "Cyclone coordinates detected",
                    },
                },
            },
        },
    }


def is_old_flat_config(config):
    return (
        isinstance(config, dict)
        and "fit_mode" in config
        and "manual_image" not in config
    )


def normalize_config(config):
    if not isinstance(config, dict):
        raise ValueError("Image rendering configuration must be a JSON object.")

    if is_old_flat_config(config):
        normalized = default_config()
        normalized["manual_image"] = {
            "fit_mode": config.get("fit_mode"),
            "target_width": config.get("target_width"),
            "target_height": config.get("target_height"),
        }

        for key, value in config.items():
            if key not in {"fit_mode", "target_width", "target_height"}:
                normalized[key] = copy.deepcopy(value)
    else:
        normalized = copy.deepcopy(config)

    framing = (
        normalized.get("auto_map", {})
        .get("framing")
    )
    if not isinstance(framing, dict):
        return normalized

    regions = framing.get("regions")
    if not isinstance(regions, dict):
        return normalized

    defaults = default_config()["auto_map"]["framing"]["regions"]
    legacy_aliases = (
        (framing.get("area_routing") or {}).get("aliases") or {}
    )
    legacy_combinations = (
        (framing.get("area_routing") or {}).get("combinations") or {}
    )
    legacy_hierarchical_config = bool(
        legacy_aliases or legacy_combinations
    )
    area_routing = framing.get("area_routing")
    if isinstance(area_routing, dict) and legacy_hierarchical_config:
        area_routing.setdefault(
            "parent_group_combinations",
            copy.deepcopy(
                default_config()["auto_map"]["framing"]["area_routing"][
                    "parent_group_combinations"
                ]
            ),
        )
    for region_id, default_region in defaults.items():
        if region_id not in regions:
            if legacy_hierarchical_config:
                regions[region_id] = copy.deepcopy(default_region)
            continue

        region = regions[region_id]
        if not isinstance(region, dict):
            continue
        if legacy_hierarchical_config:
            region.setdefault(
                "parent_group",
                default_region["parent_group"],
            )
            aliases = region.get("aliases") or legacy_aliases.get(region_id)
            if not aliases:
                aliases = default_region["aliases"]
            region["aliases"] = copy.deepcopy(aliases)

    return normalized


def require_bool(value, path):
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be true or false.")


def require_number(value, path):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric.")


def validate_target_size(section, path):
    size = (section.get("target_width"), section.get("target_height"))
    if size != TARGET_SIZE:
        raise ValueError(f"{path} canvas must be 1080x1350.")


def validate_framing_entry(entry, path, regions, allow_weather_system=True):
    if not isinstance(entry, dict):
        raise ValueError(f"{path} must be an object.")

    strategy = entry.get("strategy")
    if strategy not in SUPPORTED_FRAMING_STRATEGIES:
        raise ValueError(f"{path}.strategy is unsupported.")
    if strategy == "weather_system" and not allow_weather_system:
        raise ValueError(f"{path}.strategy must be region.")

    for field in ("zoom", "pan_x", "pan_y"):
        require_number(entry.get(field), f"{path}.{field}")

    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{path}.reason must be a non-empty string.")

    if strategy == "region":
        region_id = entry.get("region_id")
        if region_id not in regions:
            raise ValueError(f"{path}.region_id is not configured.")


def validate_area_routing(area_routing, regions):
    path = "auto_map.framing.area_routing"
    if area_routing is None:
        return
    if not isinstance(area_routing, dict):
        raise ValueError(f"{path} must be an object.")

    require_bool(area_routing.get("enabled"), f"{path}.enabled")

    aliases = area_routing.get("aliases")
    combinations = area_routing.get("combinations")
    parent_combinations = area_routing.get("parent_group_combinations")
    if aliases is not None and not isinstance(aliases, dict):
        raise ValueError(f"{path}.aliases must be an object.")
    if combinations is not None and not isinstance(combinations, dict):
        raise ValueError(f"{path}.combinations must be an object.")
    if not isinstance(parent_combinations, dict):
        raise ValueError(
            f"{path}.parent_group_combinations must be an object."
        )

    for region_id, values in (aliases or {}).items():
        alias_path = f"{path}.aliases.{region_id}"
        if region_id not in regions:
            raise ValueError(f"{alias_path} references an unknown region.")
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(value, str) or not value.strip()
                for value in values
            )
        ):
            raise ValueError(f"{alias_path} must contain strings.")

    for combo_key, region_id in (combinations or {}).items():
        combo_path = f"{path}.combinations.{combo_key}"
        if not isinstance(combo_key, str) or not combo_key.strip():
            raise ValueError(f"{combo_path} must use a non-empty key.")
        combo_parts = combo_key.split("+")
        if any(part not in regions for part in combo_parts):
            raise ValueError(f"{combo_path} references an unknown region.")
        if region_id not in regions:
            raise ValueError(f"{combo_path} target region is not configured.")

    for combo_key, region_id in parent_combinations.items():
        combo_path = f"{path}.parent_group_combinations.{combo_key}"
        combo_parts = combo_key.split("+")
        if any(part not in PARENT_REGION_GROUPS for part in combo_parts):
            raise ValueError(
                f"{combo_path} must use configured parent groups."
            )
        if region_id not in regions:
            raise ValueError(f"{combo_path} target region is not configured.")


def validate_region(region_id, region):
    path = f"auto_map.framing.regions.{region_id}"
    if not isinstance(region, dict):
        raise ValueError(f"{path} must be an object.")

    parent_group = region.get("parent_group")
    if parent_group not in PARENT_REGION_GROUPS:
        raise ValueError(
            f"{path}.parent_group must be one of "
            f"{', '.join(PARENT_REGION_GROUPS)}."
        )

    aliases = region.get("aliases")
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(
            not isinstance(alias, str) or not alias.strip()
            for alias in aliases
        )
    ):
        raise ValueError(f"{path}.aliases must contain strings.")

    framing_fields = ("center_lat", "center_lon", "zoom")
    present_fields = [field for field in framing_fields if field in region]
    if present_fields and len(present_fields) != len(framing_fields):
        raise ValueError(
            f"{path} must define center_lat, center_lon, and zoom together."
        )
    for field in present_fields:
        require_number(region[field], f"{path}.{field}")
    for field in ("pan_x", "pan_y"):
        if field in region:
            require_number(region[field], f"{path}.{field}")


def validate_config(config):
    normalized = normalize_config(config)

    if not isinstance(normalized.get("version"), str):
        raise ValueError("version must be a string.")

    manual = normalized.get("manual_image")
    if not isinstance(manual, dict):
        raise ValueError("manual_image must be an object.")
    if manual.get("fit_mode") not in SUPPORTED_FIT_MODES:
        raise ValueError(
            f"Unsupported image fit mode: {manual.get('fit_mode')!r}."
        )
    validate_target_size(manual, "manual_image")

    auto_map = normalized.get("auto_map")
    if not isinstance(auto_map, dict):
        raise ValueError("auto_map must be an object.")
    require_bool(auto_map.get("enabled"), "auto_map.enabled")
    validate_target_size(auto_map, "auto_map")

    framing = auto_map.get("framing")
    if framing is not None:
        if not isinstance(framing, dict):
            raise ValueError("auto_map.framing must be an object.")
        require_bool(framing.get("enabled"), "auto_map.framing.enabled")

        regions = framing.get("regions")
        situations = framing.get("situations")
        if not isinstance(regions, dict) or not regions:
            raise ValueError("auto_map.framing.regions must not be empty.")
        if not isinstance(situations, dict):
            raise ValueError("auto_map.framing.situations must be an object.")

        required_regions = set(REQUIRED_BROAD_REGIONS) | set(
            REQUIRED_SUBREGIONS
        )
        missing_regions = sorted(required_regions - set(regions))
        if missing_regions:
            raise ValueError(
                "Missing required framing regions: "
                + ", ".join(missing_regions)
            )

        for region_id, region in regions.items():
            validate_region(region_id, region)

        for region_id in REQUIRED_BROAD_REGIONS:
            region = regions[region_id]
            if not all(
                field in region
                for field in ("center_lat", "center_lon", "zoom")
            ):
                raise ValueError(
                    f"auto_map.framing.regions.{region_id} "
                    "requires dedicated framing."
                )

        validate_area_routing(framing.get("area_routing"), regions)

        validate_framing_entry(
            framing.get("default"),
            "auto_map.framing.default",
            regions,
            allow_weather_system=False,
        )

        for situation_id, situation in situations.items():
            path = f"auto_map.framing.situations.{situation_id}"
            validate_framing_entry(situation, path, regions)
            aliases = situation.get("aliases")
            if aliases is not None and (
                not isinstance(aliases, list)
                or any(
                    not isinstance(alias, str) or not alias.strip()
                    for alias in aliases
                )
            ):
                raise ValueError(f"{path}.aliases must contain strings.")

    return normalized


def validate_upload_size(path):
    if Path(path).stat().st_size > MAX_IMAGE_RENDERING_UPLOAD_BYTES:
        raise ValueError("Image rendering upload rejected: file too large.")


def load_config_file(config_path=CONFIG_PATH):
    path = Path(config_path)
    validate_upload_size(path)
    raw_config = json.loads(path.read_text(encoding="utf-8"))
    return validate_config(raw_config)


def reload_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_config_file(CONFIG_PATH)
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return _config_cache


def load_config(config_path=CONFIG_PATH):
    global _config_cache, _last_loaded, _last_validation_error
    path = Path(config_path)

    if path == CONFIG_PATH and _config_cache is not None:
        return copy.deepcopy(_config_cache)

    if not path.exists():
        return default_config()

    try:
        config = load_config_file(path)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        LOGGER.warning(
            "Invalid image rendering configuration; using safe fallback: %s",
            error,
        )
        _last_validation_error = str(error)
        if path == CONFIG_PATH and _config_cache is not None:
            return copy.deepcopy(_config_cache)
        return default_config()

    if path == CONFIG_PATH:
        _config_cache = config
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        _last_validation_error = None

    return copy.deepcopy(config)


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

    if path == CONFIG_PATH:
        reload_config()

    return copy.deepcopy(validated)


def set_fit_mode(mode, config_path=CONFIG_PATH):
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in SUPPORTED_FIT_MODES:
        raise ValueError(
            "Unsupported mode. Use stretch, smartfit, or crop."
        )

    config = load_config(config_path)
    config["manual_image"]["fit_mode"] = normalized_mode
    return save_config(config, config_path=config_path)


def count_backups():
    if not BACKUP_DIR.exists():
        return 0
    return len(list(BACKUP_DIR.glob("image_rendering.*.json")))


def get_image_rendering_status(config_path=CONFIG_PATH):
    config = load_config(config_path)
    manual = config["manual_image"]
    auto_map = config["auto_map"]
    framing = auto_map.get("framing") or {}
    regions = framing.get("regions") or {}

    if Path(config_path) == CONFIG_PATH:
        try:
            load_config_file(CONFIG_PATH)
            validation_status = "valid"
            validation_error = None
        except Exception as error:
            validation_status = "invalid"
            validation_error = str(error)
    else:
        validation_status = "valid"
        validation_error = None

    return {
        "config_path": str(CONFIG_PATH.relative_to(BASE_DIR)),
        "version": config.get("version"),
        "validation_status": validation_status,
        "last_loaded": _last_loaded,
        "last_validation_error": (
            validation_error or _last_validation_error
        ),
        "fit_mode": manual["fit_mode"],
        "target_width": manual["target_width"],
        "target_height": manual["target_height"],
        "available_modes": SUPPORTED_FIT_MODES,
        "auto_map_enabled": auto_map.get("enabled", False),
        "framing_enabled": framing.get("enabled", False),
        "default_framing": framing.get("default", {}),
        "framing_situations": tuple(
            (framing.get("situations") or {}).keys()
        ),
        "area_routing_enabled": (
            (framing.get("area_routing") or {}).get("enabled", False)
        ),
        "area_routing_aliases": tuple(
            region_id
            for region_id, region in regions.items()
            if region.get("aliases")
        ),
        "area_routing_combinations": tuple(
            (
                (framing.get("area_routing") or {})
                .get("parent_group_combinations")
                or {}
            ).keys()
        ),
        "hierarchical_region_count": len(regions),
        "parent_fallback_regions": tuple(
            region_id
            for region_id, region in regions.items()
            if not all(
                field in region
                for field in ("center_lat", "center_lon", "zoom")
            )
        ),
        "backup_count": count_backups(),
    }


def config_json_preview(limit=3500):
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("Image rendering configuration does not exist.")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n\n... shortened preview ..."


def starter_config_json():
    return json.dumps(default_config(), indent=2)


def backup_current_config():
    if not CONFIG_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    backup_path = BACKUP_DIR / f"image_rendering.{timestamp}.json"
    backup_path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    backups = sorted(
        BACKUP_DIR.glob("image_rendering.*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_IMAGE_RENDERING_BACKUPS:]:
        old_backup.unlink()
    return backup_path


def replace_config_from_file(uploaded_path):
    config = load_config_file(uploaded_path)
    backup_current_config()
    save_config(config, CONFIG_PATH)
    return get_image_rendering_status()


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
    config = load_config(config_path)
    manual = config["manual_image"]
    target_size = (
        manual["target_width"],
        manual["target_height"],
    )
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    mode = manual["fit_mode"]

    try:
        if mode == "stretch":
            return stretch(prepared, target_size)
        if mode == "crop":
            return crop(prepared, target_size)
        return smartfit(prepared, target_size)
    except Exception as error:
        LOGGER.warning(
            "Image rendering failed in %s mode; using smartfit: %s",
            mode,
            error,
        )
        return smartfit(prepared, target_size)


def render_manual_image(input_path, output_path=None, config_path=CONFIG_PATH):
    source_path = Path(input_path)
    destination_path = Path(output_path) if output_path else source_path

    with Image.open(source_path) as image:
        rendered = apply_image_fit(image, config_path=config_path)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(destination_path, format="JPEG", quality=95)
    return str(destination_path)
