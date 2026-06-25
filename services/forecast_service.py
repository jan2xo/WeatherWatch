import re


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
        "keywords": [
            "low pressure area",
            "lpa",
        ],
    },
    {
        "type": "habagat",
        "keywords": [
            "southwest monsoon",
            "habagat",
        ],
    },
    {
        "type": "amihan",
        "keywords": [
            "northeast monsoon",
            "amihan",
        ],
    },
    {
        "type": "thunderstorm",
        "keywords": [
            "localized thunderstorms",
            "thunderstorms",
        ],
    },
]


STORM_DETAIL_PATTERN = re.compile(
    r'the center of\s+'
    r'(Super Typhoon|Typhoon|Severe Tropical Storm|Tropical Storm|Tropical Depression)\s+'
    r'"?([A-Z\s]+)"?.*?'
    r'at\s+([\d,]+)\s+km\s+(.+?)\.'
    r'(?:.*?maximum sustained winds of\s+(\d+)\s+km/h.*?gustiness of up to\s+(\d+)\s+km/h\.)?'
    r'(?:.*?moving\s+(.+?)\s+at\s+(\d+)\s+km/h\.)?',
    re.IGNORECASE | re.DOTALL,
)


STORM_PATTERN = re.compile(
    r'(Super Typhoon|Typhoon|Severe Tropical Storm|Tropical Storm|Tropical Depression)\s+"?([A-Z\s]+)"?',
    re.IGNORECASE,
)


def format_storm_name(name: str) -> str:
    """
    FRANCISCO -> Francisco
    """
    return name.strip().title().replace(" ", "")


def make_storm_hashtag(name: str) -> str:
    """
    FRANCISCO -> #FranciscoPH
    """
    return f"#{format_storm_name(name)}PH"


def detect_weather_type(text: str) -> str:
    lowered = text.lower()

    for rule in FORECAST_RULES:
        for keyword in rule["keywords"]:
            if keyword in lowered:
                return rule["type"]

    return "general_weather"


def extract_bulletin_lines(text: str):
    """
    Convert recurring PAGASA English bulletin lines into
    WeatherWatch newsroom Filipino.
    """

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
            "location": match.group(4).strip(),

            "sustained_winds_kmh": match.group(5),
            "gustiness_kmh": match.group(6),

            "movement_direction": match.group(7).strip() if match.group(7) else None,
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

    return {
        "raw_text": text,
        "weather_type": detect_weather_type(text),

        "storms": storms,
        "has_storms": len(storms) > 0,

        "bulletin_lines": extract_bulletin_lines(text),

        "habagat": "southwest monsoon" in lowered or "habagat" in lowered,
        "amihan": "northeast monsoon" in lowered or "amihan" in lowered,
        "lpa": "low pressure area" in lowered or "lpa" in lowered,
        "thunderstorm": "thunderstorm" in lowered,
    }