import logging

from services.image_rendering_service import (
    default_config,
    load_config,
    validate_config,
)


LOGGER = logging.getLogger(__name__)


def normalize(value):
    return " ".join(str(value or "").strip().casefold().split())


def coordinates_from(forecast_data):
    latitude = forecast_data.get("latitude")
    longitude = forecast_data.get("longitude")

    if (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
    ):
        return latitude, longitude

    return None


def resolve_entry(
    entry,
    framing,
    situation_id,
    coordinates=None,
    detected_situation_id=None,
):
    strategy = entry["strategy"]
    decision = {
        "enabled": True,
        "strategy": strategy,
        "center_lat": None,
        "center_lon": None,
        "zoom": entry["zoom"],
        "pan_x": entry.get("pan_x", 0),
        "pan_y": entry.get("pan_y", 0),
        "region_id": entry.get("region_id"),
        "situation_id": situation_id,
        "reason": entry["reason"],
    }

    if detected_situation_id:
        decision["detected_situation_id"] = detected_situation_id
        decision["fallback_used"] = True

    if strategy == "region":
        region = framing["regions"][entry["region_id"]]
        decision["center_lat"] = region["center_lat"]
        decision["center_lon"] = region["center_lon"]
    elif coordinates:
        decision["center_lat"], decision["center_lon"] = coordinates
        if "include_nearest_landmass" in entry:
            decision["include_nearest_landmass"] = entry[
                "include_nearest_landmass"
            ]

    return decision


def default_decision(auto_map, detected_situation_id=None):
    framing = auto_map["framing"]
    decision = resolve_entry(
        framing["default"],
        framing,
        situation_id="default",
        detected_situation_id=detected_situation_id,
    )
    decision["enabled"] = bool(
        auto_map.get("enabled") and framing.get("enabled")
    )
    return decision


def aliases_for(situation_id, situation):
    return {
        normalize(situation_id),
        *(
            normalize(alias)
            for alias in situation.get("aliases", [])
        ),
    }


def detect_situation(parsed_forecast_text, forecast_data, situations):
    coordinates = coordinates_from(forecast_data)
    cyclone_fields = (
        forecast_data.get("cyclone_classification"),
        forecast_data.get("cyclone_name_local"),
    )

    if all(cyclone_fields) and coordinates and "cyclone" in situations:
        return "cyclone"

    affected_system = normalize(
        forecast_data.get("affected_weather_system")
    )
    if affected_system:
        for situation_id, situation in situations.items():
            if affected_system in aliases_for(situation_id, situation):
                return situation_id

    raw_text = normalize(parsed_forecast_text)
    lpa = situations.get("lpa")
    if lpa and any(
        alias and alias in raw_text
        for alias in aliases_for("lpa", lpa)
    ):
        return "lpa"

    for situation_id, situation in situations.items():
        if any(
            alias and alias in raw_text
            for alias in aliases_for(situation_id, situation)
        ):
            return situation_id

    return None


def determine_map_framing(
    forecast_data,
    parsed_forecast_text="",
    image_config=None,
):
    data = forecast_data if isinstance(forecast_data, dict) else {}

    try:
        config = (
            validate_config(image_config)
            if image_config is not None
            else load_config()
        )
        auto_map = config["auto_map"]
        framing = auto_map.get("framing")
        if not framing:
            return {
                "enabled": False,
                "strategy": "region",
                "situation_id": "default",
                "reason": "Map framing is not configured",
            }

        situations = framing["situations"]
        situation_id = detect_situation(
            parsed_forecast_text,
            data,
            situations,
        )

        if not situation_id:
            return default_decision(auto_map)

        situation = situations[situation_id]
        coordinates = coordinates_from(data)
        if situation["strategy"] == "weather_system" and not coordinates:
            return default_decision(
                auto_map,
                detected_situation_id=situation_id,
            )

        decision = resolve_entry(
            situation,
            framing,
            situation_id=situation_id,
            coordinates=coordinates,
        )
        decision["enabled"] = bool(
            auto_map.get("enabled") and framing.get("enabled")
        )
        return decision
    except Exception as error:
        LOGGER.warning(
            "Map framing configuration failed; using safe default: %s",
            error,
        )
        safe_auto_map = default_config()["auto_map"]
        return default_decision(safe_auto_map)
