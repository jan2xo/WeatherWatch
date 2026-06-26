import re

from services.forecast_parser import (
    build_affected_weather_caption_detail,
    build_structured_forecast_caption_detail,
    parse_pagasa_forecast_text,
)


FORECAST_RULES = [
    {
        "type": "tropical_cyclone",
        "keywords": [
            "super typhoon",
            "typhoon",
            "severe tropical storm",
            "tropical storm",
            "tropical depression",
        ],
    },
    {
        "type": "lpa",
        "keywords": ["low pressure area", "lpa"],
    },
    {
        "type": "habagat",
        "keywords": ["southwest monsoon", "habagat"],
    },
    {
        "type": "amihan",
        "keywords": ["northeast monsoon", "amihan"],
    },
    {
        "type": "thunderstorm",
        "keywords": ["localized thunderstorms", "thunderstorms"],
    },
]


STORM_DETAIL_PATTERN = re.compile(
    r'the center of\s+'
    r'(Super Typhoon|Typhoon|Severe Tropical Storm|Tropical Storm|Tropical Depression)\s+'
    r'"?([A-Z\s]+)"?.*?'
    r'at\s+([\d,]+)\s+km\s+'
    r'(.+?)\s+'
    r'with maximum sustained winds of\s+(\d+)\s+km/h.*?'
    r'gustiness of up to\s+(\d+)\s+km/h\.\s+'
    r'It is moving\s+(.+?)\s+at\s+(\d+)\s+km/h\.',
    re.IGNORECASE | re.DOTALL,
)


STORM_PATTERN = re.compile(
    r'(Super Typhoon|Typhoon|Severe Tropical Storm|Tropical Storm|Tropical Depression)\s+"?([A-Z\s]+)"?',
    re.IGNORECASE,
)


def format_storm_name(name: str) -> str:
    return name.strip().title().replace(" ", "")


def make_storm_hashtag(name: str) -> str:
    return f"#{format_storm_name(name)}PH"


def detect_weather_type(text: str) -> str:
    lowered = text.lower()

    for rule in FORECAST_RULES:
        for keyword in rule["keywords"]:
            if keyword in lowered:
                return rule["type"]

    return "general_weather"


def clean_location(location: str) -> str:
    return " ".join(location.strip().split())


def extract_bulletin_lines(text: str):
    lines = []

    translations = {
        "Southwest Monsoon affecting Luzon and Visayas.":
            "Samantala, nakaaapekto rin ang Habagat sa Luzon at Visayas.",
        "Southwest Monsoon affecting Luzon.":
            "Samantala, nakaaapekto rin ang Habagat sa Luzon.",
        "Southwest Monsoon affecting Visayas.":
            "Samantala, nakaaapekto rin ang Habagat sa Visayas.",
        "Northeast Monsoon affecting Luzon.":
            "Samantala, nakaaapekto rin ang Amihan sa Luzon.",
    }

    for english, filipino in translations.items():
        if english in text:
            lines.append(filipino)

    return lines


def extract_storms(text: str):
    storms = []

    for match in STORM_DETAIL_PATTERN.finditer(text):
        category = match.group(1).strip()
        name = match.group(2).strip().upper()

        storms.append({
            "name": name,
            "display_name": format_storm_name(name),
            "category": category,
            "hashtag": make_storm_hashtag(name),

            "distance_km": match.group(3).replace(",", "").strip(),
            "location": clean_location(match.group(4)),

            "sustained_winds_kmh": match.group(5),
            "gustiness_kmh": match.group(6),

            "movement_direction": match.group(7).strip(),
            "movement_speed_kmh": match.group(8),
        })

    if storms:
        return storms

    for match in STORM_PATTERN.finditer(text):
        category = match.group(1).strip()
        name = match.group(2).strip().upper()

        storms.append({
            "name": name,
            "display_name": format_storm_name(name),
            "category": category,
            "hashtag": make_storm_hashtag(name),

            "distance_km": None,
            "location": None,

            "sustained_winds_kmh": None,
            "gustiness_kmh": None,

            "movement_direction": None,
            "movement_speed_kmh": None,
        })

    return storms


def parse_forecast_text(text: str):
    lowered = text.lower()
    storms = extract_storms(text)
    structured = parse_pagasa_forecast_text(text)

    return {
        "raw_text": text,
        "structured": structured,
        "structured_caption_detail": build_structured_forecast_caption_detail(structured),
        "affected_weather_caption_detail": build_affected_weather_caption_detail(structured),
        "weather_type": detect_weather_type(text),

        "storms": storms,
        "has_storms": len(storms) > 0,

        "bulletin_lines": extract_bulletin_lines(text),

        "habagat": "southwest monsoon" in lowered or "habagat" in lowered,
        "amihan": "northeast monsoon" in lowered or "amihan" in lowered,
        "lpa": "low pressure area" in lowered or "lpa" in lowered,
        "thunderstorm": "thunderstorm" in lowered,
    }
