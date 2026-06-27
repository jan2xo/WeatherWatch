import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.content_composer_service import compose_weather_content
from services.content_service import build_facebook_caption, build_graphic_headline
from services.forecast_parser import parse_pagasa_forecast_text
from services.forecast_service import parse_forecast_text


MONSOON_TEXT = "Southwest Monsoon affecting Luzon and Visayas."
CYCLONE_TEXT = (
    'At 3:00 AM today, the center of Severe Tropical Storm "GARDO" {HIGOS} '
    "was estimated based on all available data at 1,285 km East of Extreme Northern Luzon "
    "(22.5°N, 134.1°E) with maximum sustained winds of 95 km/h near the center "
    "and gustiness of up to 115 km/h. It is moving North Northwestward at 25 km/h. "
    "Southwest Monsoon affecting Luzon and Visayas."
)


def verify_monsoon_update():
    forecast = parse_forecast_text(MONSOON_TEXT)
    content = forecast["composed_content"]

    assert content["content_type"] == "monsoon_update"
    assert content["headline"] == "Habagat Nakaaapekto sa Luzon at Visayas"
    assert "Luzon at Visayas" in content["summary"]
    assert "cyclone" not in content["summary"].lower()
    assert "bagyo" not in content["summary"].lower()

    job = {
        "forecast": forecast,
        "provider": "windy",
        "provider_display": "WINDY",
        "provider_url": "windy.com",
    }
    job["headline"] = build_graphic_headline(job)
    caption = build_facebook_caption(job)

    assert job["headline"] == "HABAGAT\nNAKAAAPEKTO SA LUZON AT VISAYAS"
    assert "HABAGAT NAKAAAPEKTO SA LUZON AT VISAYAS!" in caption
    assert "Forecast: PAGASA | pagasa.dost.gov.ph" in caption
    assert "Map: WINDY | windy.com" in caption
    assert "Batay sa pinakahuling weather bulletin ng PAGASA:" not in caption


def verify_cyclone_update():
    data = parse_pagasa_forecast_text(CYCLONE_TEXT)
    content = compose_weather_content(CYCLONE_TEXT, data)
    story = " ".join([content["summary"], *content["body_lines"]])

    assert content["content_type"] == "cyclone_update"
    assert "95 km/h" in story
    assert "115 km/h" in story
    assert "25 km/h" in story
    assert "#GardoPH" in content["headline"]


def verify_fallback_update():
    content = compose_weather_content(
        "Cloudy skies were observed.",
        {},
    )

    assert content["content_type"] == "general_weather"
    assert "PAGASA" in content["summary"]
    assert content["headline"]


def main():
    verify_monsoon_update()
    verify_cyclone_update()
    verify_fallback_update()
    print("content composer verification ok")


if __name__ == "__main__":
    main()
