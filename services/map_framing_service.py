import logging

from services.image_rendering_service import (
    default_config,
    load_config,
    validate_config,
)


LOGGER = logging.getLogger(__name__)
PARENT_GROUP_PRIORITY = (
    "philippines",
    "luzon",
    "visayas",
    "mindanao",
)


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


def build_region_framing_decision(
    region_id,
    framing,
    situation_id=None,
    reason=None,
    source="affected_area",
    matched_areas=None,
    matched_regions=None,
    resolved_parent_groups=None,
    fallback_used=False,
    fallback_reason=None,
):
    region = framing["regions"][region_id]
    decision = {
        "enabled": True,
        "strategy": "region",
        "center_lat": region["center_lat"],
        "center_lon": region["center_lon"],
        "zoom": region["zoom"],
        "pan_x": region.get("pan_x", 0),
        "pan_y": region.get("pan_y", 0),
        "region_id": region_id,
        "situation_id": situation_id,
        "source": source,
        "matched_areas": matched_areas or [],
        "matched_regions": matched_regions or [],
        "resolved_parent_groups": resolved_parent_groups or [],
        "matched_region_id": region_id,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "reason": reason or f"Region framing matched {region_id}",
    }
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
    decision["source"] = "default"
    decision["matched_areas"] = []
    decision["matched_regions"] = []
    decision["resolved_parent_groups"] = []
    decision["matched_region_id"] = decision.get("region_id")
    decision["fallback_used"] = bool(detected_situation_id)
    decision["fallback_reason"] = (
        f"{detected_situation_id} could not provide reliable coordinates; "
        "using configured default framing"
        if detected_situation_id
        else None
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


def normalize_area_for_framing(area_text):
    return normalize(area_text)


def match_area_to_region(area_text, framing_config):
    normalized_area = normalize_area_for_framing(area_text)
    if not normalized_area:
        return None

    matches = []
    for region_id, region in framing_config.get("regions", {}).items():
        for alias in region.get("aliases", []):
            normalized_alias = normalize_area_for_framing(alias)
            if not normalized_alias:
                continue
            if (
                normalized_alias == normalized_area
                or normalized_alias in normalized_area
            ):
                matches.append({
                    "region_id": region_id,
                    "alias": alias,
                    "exact": normalized_alias == normalized_area,
                    "length": len(normalized_alias),
                })

    if not matches:
        return None

    matches.sort(
        key=lambda item: (item["exact"], item["length"]),
        reverse=True,
    )
    return matches[0]["region_id"]


def resolve_region_parent_group(region_id, framing_config):
    region = framing_config.get("regions", {}).get(region_id) or {}
    return region.get("parent_group")


def region_has_dedicated_framing(region_id, framing_config):
    region = framing_config.get("regions", {}).get(region_id) or {}
    return all(
        isinstance(region.get(field), (int, float))
        and not isinstance(region.get(field), bool)
        for field in ("center_lat", "center_lon", "zoom")
    )


def parent_group_combination_key(parent_groups):
    ordered = [
        parent_group
        for parent_group in PARENT_GROUP_PRIORITY
        if parent_group in parent_groups
    ]
    remaining = sorted(set(parent_groups) - set(ordered))
    return "+".join([*ordered, *remaining])


def resolve_parent_group_combination(parent_groups, framing_config):
    groups = set(parent_groups)
    if "philippines" in groups:
        return "philippines"
    if len(groups) == 1:
        return next(iter(groups))

    combinations = (
        framing_config.get("area_routing", {})
        .get("parent_group_combinations", {})
    )
    return combinations.get(parent_group_combination_key(groups))


def affected_area_candidates(forecast_data):
    area_lists = [
        forecast_data.get("affected_areas_headline") or [],
        forecast_data.get("affected_areas_short") or [],
        forecast_data.get("affected_areas") or [],
        forecast_data.get("affected_areas_original") or [],
    ]
    area_count = max((len(areas) for areas in area_lists), default=0)

    for index in range(area_count):
        candidates = []
        for areas in area_lists:
            if index >= len(areas):
                continue
            area = str(areas[index]).strip()
            if area and area not in candidates:
                candidates.append(area)
        yield candidates


def resolve_affected_area_region(forecast_data, framing_config):
    area_routing = framing_config.get("area_routing") or {}
    if not area_routing.get("enabled"):
        return None

    matched_regions = []
    matched_areas = []

    for candidates in affected_area_candidates(forecast_data):
        for area in candidates:
            region_id = match_area_to_region(area, framing_config)
            if not region_id:
                continue
            matched_areas.append(area)
            if region_id not in matched_regions:
                matched_regions.append(region_id)
            break

    if not matched_regions:
        return None

    parent_groups = []
    for matched_region in matched_regions:
        parent_group = resolve_region_parent_group(
            matched_region,
            framing_config,
        )
        if parent_group and parent_group not in parent_groups:
            parent_groups.append(parent_group)

    fallback_used = False
    fallback_reason = None
    if (
        len(matched_regions) == 1
        and region_has_dedicated_framing(matched_regions[0], framing_config)
    ):
        region_id = matched_regions[0]
    else:
        region_id = resolve_parent_group_combination(
            parent_groups,
            framing_config,
        )

    if len(matched_regions) == 1 and region_id != matched_regions[0]:
        fallback_used = True
        fallback_reason = (
            f"{matched_regions[0]} has no dedicated framing; "
            f"using parent group {region_id}"
        )

    if not region_id or not region_has_dedicated_framing(
        region_id,
        framing_config,
    ):
        return None

    return {
        "region_id": region_id,
        "matched_areas": matched_areas,
        "matched_regions": matched_regions,
        "resolved_parent_groups": parent_groups,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
    }


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
        coordinates = coordinates_from(data)

        if situation_id == "cyclone" and coordinates:
            situation = situations[situation_id]
            decision = resolve_entry(
                situation,
                framing,
                situation_id=situation_id,
                coordinates=coordinates,
            )
            decision["enabled"] = bool(
                auto_map.get("enabled") and framing.get("enabled")
            )
            decision["source"] = "weather_system"
            decision["matched_areas"] = []
            decision["matched_regions"] = []
            decision["resolved_parent_groups"] = []
            decision["matched_region_id"] = decision.get("region_id")
            decision["fallback_used"] = False
            decision["fallback_reason"] = None
            return decision

        area_match = resolve_affected_area_region(
            data,
            framing,
        )
        if area_match:
            decision = build_region_framing_decision(
                area_match["region_id"],
                framing,
                situation_id=situation_id,
                source="affected_area",
                matched_areas=area_match["matched_areas"],
                matched_regions=area_match["matched_regions"],
                resolved_parent_groups=area_match[
                    "resolved_parent_groups"
                ],
                fallback_used=area_match["fallback_used"],
                fallback_reason=area_match["fallback_reason"],
                reason=(
                    "Affected area framing matched "
                    f"{area_match['region_id']}"
                ),
            )
            decision["enabled"] = bool(
                auto_map.get("enabled") and framing.get("enabled")
            )
            return decision

        if not situation_id:
            return default_decision(auto_map)

        situation = situations[situation_id]
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
        decision["source"] = "weather_system"
        decision["matched_areas"] = []
        decision["matched_regions"] = []
        decision["resolved_parent_groups"] = []
        decision["matched_region_id"] = decision.get("region_id")
        decision["fallback_used"] = False
        decision["fallback_reason"] = None
        return decision
    except Exception as error:
        LOGGER.warning(
            "Map framing configuration failed; using safe default: %s",
            error,
        )
        safe_auto_map = default_config()["auto_map"]
        return default_decision(safe_auto_map)
