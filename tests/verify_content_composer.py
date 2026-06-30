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


def verify_configured_weather_systems():
    cases = [
        (
            "Northeast Monsoon",
            "Northeast Monsoon affecting Northern Luzon.",
            "Amihan",
            "monsoon_update",
        ),
        (
            "Intertropical Convergence Zone",
            "Intertropical Convergence Zone affecting Mindanao.",
            "ITCZ",
            "convergence_zone_update",
        ),
        (
            "Low Pressure Area",
            "Low Pressure Area affecting Eastern Visayas.",
            "LPA",
            "low_pressure_area_update",
        ),
        (
            "Easterlies",
            "Easterlies affecting the eastern section of Luzon.",
            "Easterlies",
            "wind_flow_update",
        ),
        (
            "Shear Line",
            "Shear Line affecting Northern Luzon.",
            "Shear Line",
            "boundary_update",
        ),
        (
            "Frontal System",
            "Tail-end of a Frontal System affecting Northern Luzon.",
            "Frontal System",
            "boundary_update",
        ),
    ]

    for system_name, text, expected_name, content_type in cases:
        forecast = parse_forecast_text(text)
        content = forecast["composed_content"]
        assert content["content_type"] == content_type
        assert expected_name in content["headline"]
        assert expected_name in (
            content["summary"] + " " + content["headline"]
        )
        assert forecast["structured"]["affected_weather_system"]

        job = {
            "forecast": forecast,
            "provider": "windy",
            "provider_display": "WINDY",
            "provider_url": "windy.com",
        }
        job["headline"] = build_graphic_headline(job)
        caption = build_facebook_caption(job)
        assert expected_name.upper() in job["headline"]
        assert content["summary"] in caption


def verify_missing_areas_and_unknown_system():
    missing_areas = compose_weather_content(
        "Northeast Monsoon remains active.",
        {"affected_weather_system": "Northeast Monsoon"},
    )
    assert missing_areas["headline"] == "Amihan"
    assert missing_areas["summary"]
    assert not missing_areas["headline"].endswith("sa")
    assert "sa ." not in missing_areas["summary"].casefold()

    unknown = compose_weather_content(
        "Unknown circulation affecting Luzon.",
        {
            "affected_weather_system": "Unknown Circulation",
            "affected_areas": ["Luzon"],
        },
    )
    assert unknown["content_type"] == "general_weather"
    assert unknown["headline"] == "Weather Update"


def main():
    verify_monsoon_update()
    verify_cyclone_update()
    verify_fallback_update()
    verify_configured_weather_systems()
    verify_missing_areas_and_unknown_system()
    print("content composer verification ok")


if __name__ == "__main__":
    main()
