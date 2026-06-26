import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.forecast_parser import parse_pagasa_forecast_text
from services.caption_template_service import validate_template_file


SAMPLE_TEXT = (
    'At 3:00 AM today, the center of Severe Tropical Storm "GARDO" {HIGOS} '
    "was estimated based on all available data at 1,285 km East of Extreme Northern Luzon "
    "(22.5°N, 134.1°E) with maximum sustained winds of 95 km/h near the center "
    "and gustiness of up to 115 km/h. It is moving North Northwestward at 25 km/h. "
    "Southwest Monsoon affecting Luzon and Visayas."
)


def main():
    validate_template_file()
    forecast = parse_pagasa_forecast_text(SAMPLE_TEXT)

    assert forecast["maximum_sustained_winds_kmh"] == 95
    assert forecast["gustiness_kmh"] == 115
    assert forecast["movement_speed_kmh"] == 25
    assert forecast["cyclone_name_local"] == "GARDO"
    assert forecast["cyclone_name_international"] == "HIGOS"
    assert forecast["cyclone_classification"] == "Severe Tropical Storm"

    print("forecast parser verification ok")


if __name__ == "__main__":
    main()
