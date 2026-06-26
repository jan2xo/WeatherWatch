import re

from services.caption_template_service import render_template, translate


ADVISORY_TIME_PATTERN = re.compile(
    r"At\s+(.+?),\s+the center of",
    re.IGNORECASE | re.DOTALL,
)

CYCLONE_PATTERN = re.compile(
    r"the center of\s+"
    r"(Super Typhoon|Typhoon|Severe Tropical Storm|Tropical Storm|Tropical Depression)\s+"
    r'"?([A-Z\s]+)"?\s*'
    r"(?:\{([A-Z\s]+)\})?",
    re.IGNORECASE,
)

LOCATION_PATTERN = re.compile(
    r"at\s+([\d,]+\s+km\s+.+?)\s+"
    r"\(([-+]?\d+(?:\.\d+)?)\s*°?\s*N,\s*([-+]?\d+(?:\.\d+)?)\s*°?\s*E\)",
    re.IGNORECASE | re.DOTALL,
)

WIND_PATTERN = re.compile(
    r"maximum sustained winds of\s+(\d+)\s+km/h.*?"
    r"gustiness of up to\s+(\d+)\s+km/h",
    re.IGNORECASE | re.DOTALL,
)

MOVEMENT_PATTERN = re.compile(
    r"It is moving\s+(.+?)\s+at\s+(\d+)\s+km/h",
    re.IGNORECASE | re.DOTALL,
)

WEATHER_SYSTEM_PATTERN = re.compile(
    r"(Southwest Monsoon|Northeast Monsoon|Shear Line|Intertropical Convergence Zone|Localized Thunderstorms)\s+"
    r"affecting\s+(.+?)(?:\.|$)",
    re.IGNORECASE | re.DOTALL,
)


def clean_spaces(value):
    if not value:
        return None

    return " ".join(value.strip().split())


def parse_int(value):
    if not value:
        return None

    return int(value.replace(",", ""))


def parse_float(value):
    if not value:
        return None

    return float(value)


def split_affected_areas(value):
    if not value:
        return []

    normalized = re.sub(r"\s+and\s+", ",", value, flags=re.IGNORECASE)
    return [
        clean_spaces(area)
        for area in normalized.split(",")
        if clean_spaces(area)
    ]


def normalize_compass_location(location_text):
    if not location_text:
        return None

    replacements = {
        " East of ": " silangan ng ",
        " West of ": " kanluran ng ",
        " North of ": " hilaga ng ",
        " South of ": " timog ng ",
        " Northeast of ": " hilagang-silangan ng ",
        " Northwest of ": " hilagang-kanluran ng ",
        " Southeast of ": " timog-silangan ng ",
        " Southwest of ": " timog-kanluran ng ",
    }

    translated = location_text

    for english, filipino in replacements.items():
        translated = translated.replace(english, filipino)

    return translated


def format_hashtag(name):
    if not name:
        return None

    return f"#{name.title().replace(' ', '')}PH"


def format_title_name(name):
    if not name:
        return ""

    return name.title().replace(" ", "")


def translate_movement_direction(direction):
    if not direction:
        return None

    return translate("movement_directions", direction)


def translate_weather_system(system):
    if not system:
        return None

    return translate("weather_systems", system)


def safe_render_template(template_name, values, fallback):
    try:
        return render_template(template_name, values)
    except Exception:
        return fallback


def build_template_values(forecast_data, affected_areas_text=""):
    local_name = forecast_data.get("cyclone_name_local")
    international_name = forecast_data.get("cyclone_name_international")
    movement_direction = forecast_data.get("movement_direction")
    weather_system = forecast_data.get("affected_weather_system")
    translated_movement = translate_movement_direction(movement_direction)
    translated_system = translate_weather_system(weather_system)
    international_display = (
        f" {{{international_name.title()}}}"
        if international_name
        else ""
    )

    return {
        "advisory_time": forecast_data.get("advisory_time"),
        "cyclone_classification": forecast_data.get("cyclone_classification"),
        "cyclone_name_local": local_name,
        "cyclone_name_local_title": format_hashtag(local_name),
        "cyclone_name_international": international_name,
        "international_name_display": international_display,
        "location_text": normalize_compass_location(forecast_data.get("location_text")),
        "latitude": forecast_data.get("latitude"),
        "longitude": forecast_data.get("longitude"),
        "maximum_sustained_winds_kmh": forecast_data.get("maximum_sustained_winds_kmh"),
        "gustiness_kmh": forecast_data.get("gustiness_kmh"),
        "movement_direction": movement_direction,
        "movement_direction_fil": translated_movement,
        "movement_speed_kmh": forecast_data.get("movement_speed_kmh"),
        "affected_weather_system": weather_system,
        "affected_weather_system_fil": translated_system,
        "affected_areas_text": affected_areas_text,
        "classification": forecast_data.get("cyclone_classification"),
        "hashtag": format_hashtag(local_name),
        "international_name": international_display,
        "weather_system": translated_system,
        "affected_areas": affected_areas_text,
    }


def parse_pagasa_forecast_text(text: str) -> dict:
    data = {
        "advisory_time": None,
        "cyclone_classification": None,
        "cyclone_name_local": None,
        "cyclone_name_international": None,
        "location_text": None,
        "latitude": None,
        "longitude": None,
        "maximum_sustained_winds_kmh": None,
        "gustiness_kmh": None,
        "movement_direction": None,
        "movement_speed_kmh": None,
        "affected_weather_system": None,
        "affected_areas": [],
    }

    if not text:
        return data

    advisory_match = ADVISORY_TIME_PATTERN.search(text)
    if advisory_match:
        data["advisory_time"] = clean_spaces(advisory_match.group(1))

    cyclone_match = CYCLONE_PATTERN.search(text)
    if cyclone_match:
        data["cyclone_classification"] = clean_spaces(cyclone_match.group(1))
        data["cyclone_name_local"] = clean_spaces(cyclone_match.group(2)).upper()

        if cyclone_match.group(3):
            data["cyclone_name_international"] = clean_spaces(cyclone_match.group(3)).upper()

    location_match = LOCATION_PATTERN.search(text)
    if location_match:
        data["location_text"] = clean_spaces(location_match.group(1))
        data["latitude"] = parse_float(location_match.group(2))
        data["longitude"] = parse_float(location_match.group(3))

    wind_match = WIND_PATTERN.search(text)
    if wind_match:
        data["maximum_sustained_winds_kmh"] = parse_int(wind_match.group(1))
        data["gustiness_kmh"] = parse_int(wind_match.group(2))

    movement_match = MOVEMENT_PATTERN.search(text)
    if movement_match:
        data["movement_direction"] = clean_spaces(movement_match.group(1))
        data["movement_speed_kmh"] = parse_int(movement_match.group(2))

    weather_system_match = WEATHER_SYSTEM_PATTERN.search(text)
    if weather_system_match:
        data["affected_weather_system"] = clean_spaces(weather_system_match.group(1))
        data["affected_areas"] = split_affected_areas(weather_system_match.group(2))

    return data


def build_structured_forecast_caption_detail(forecast_data):
    classification = forecast_data.get("cyclone_classification")
    local_name = forecast_data.get("cyclone_name_local")
    international_name = forecast_data.get("cyclone_name_international")
    location_text = forecast_data.get("location_text")
    sustained = forecast_data.get("maximum_sustained_winds_kmh")
    gustiness = forecast_data.get("gustiness_kmh")
    movement_direction = forecast_data.get("movement_direction")
    movement_speed = forecast_data.get("movement_speed_kmh")

    if not classification or not local_name:
        return ""

    hashtag = format_hashtag(local_name)
    international = f" {{{international_name.title()}}}" if international_name else ""
    values = build_template_values(forecast_data)
    lines = []

    if location_text:
        normalized_location = normalize_compass_location(location_text)
        fallback = (
            "Batay sa pinakahuling tala ng PAGASA, "
            f"si {classification} {hashtag}{international} ay namataan sa layong "
            f"{normalized_location}."
        )
        lines.append(safe_render_template("cyclone_location", values, fallback))

    if sustained is not None and gustiness is not None:
        fallback = (
            f"Taglay nito ang maximum sustained winds na {sustained} km/h malapit sa gitna "
            f"at pagbugsong umaabot sa {gustiness} km/h."
        )
        lines.append(safe_render_template("cyclone_intensity", values, fallback))

    if movement_direction and movement_speed is not None:
        translated_direction = translate_movement_direction(movement_direction)
        fallback = (
            f"Kumikilos ito {translated_direction} sa bilis na {movement_speed} km/h."
        )
        lines.append(safe_render_template("cyclone_movement", values, fallback))

    return "\n\n".join(lines)


def build_affected_weather_caption_detail(forecast_data):
    system = translate_weather_system(forecast_data.get("affected_weather_system"))
    areas = forecast_data.get("affected_areas", [])

    if not system or not areas:
        return ""

    if len(areas) == 1:
        area_text = areas[0]
    else:
        area_text = " at ".join([
            ", ".join(areas[:-1]),
            areas[-1],
        ])

    fallback = f"Samantala, nakaaapekto rin ang {system} sa {area_text}."
    return safe_render_template(
        "affected_system",
        build_template_values(forecast_data, affected_areas_text=area_text),
        fallback,
    )
