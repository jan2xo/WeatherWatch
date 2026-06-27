import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.image_rendering_service import (
    default_config,
    load_config,
    load_config_file,
    save_config,
    set_fit_mode,
    validate_upload_size,
)
from services.capture_service import apply_windy_framing, resolve_capture_url
from services.map_framing_service import determine_map_framing


def assert_region(text, system, expected_region):
    decision = determine_map_framing(
        {
            "affected_weather_system": system,
            "affected_areas": [],
        },
        text,
    )
    assert decision["region_id"] == expected_region
    assert decision["strategy"] == "region"


def main():
    assert_region(
        "Southwest Monsoon affecting Luzon and Visayas.",
        "Southwest Monsoon",
        "luzon_visayas",
    )
    assert_region(
        "Amihan affecting Northern Luzon.",
        "Amihan",
        "northern_luzon",
    )

    lpa = determine_map_framing(
        {"latitude": 14.0, "longitude": 128.0},
        "A Low Pressure Area was detected.",
    )
    assert lpa["situation_id"] == "lpa"
    assert lpa["strategy"] == "weather_system"
    assert lpa["center_lat"] == 14.0
    assert lpa["center_lon"] == 128.0

    lpa_without_coordinates = determine_map_framing(
        {},
        "A Low Pressure Area was detected.",
    )
    assert lpa_without_coordinates["situation_id"] == "default"
    assert lpa_without_coordinates["detected_situation_id"] == "lpa"
    assert lpa_without_coordinates["fallback_used"] is True

    cyclone = determine_map_framing(
        {
            "cyclone_classification": "Typhoon",
            "cyclone_name_local": "TEST",
            "latitude": 18.5,
            "longitude": 130.25,
        },
        "Typhoon TEST",
    )
    assert cyclone["situation_id"] == "cyclone"
    assert cyclone["center_lat"] == 18.5
    assert cyclone["center_lon"] == 130.25
    assert cyclone["zoom"] == 5

    unknown = determine_map_framing({}, "Unknown weather condition.")
    assert unknown["situation_id"] == "default"
    assert unknown["region_id"] == "philippines"

    framed_url = apply_windy_framing(
        "https://www.windy.com/-Satellite-satellite?satellite,11.001,125.321,5",
        {
            "enabled": True,
            "center_lat": 13.5,
            "center_lon": 122.5,
            "zoom": 7,
            "pan_x": 1.25,
            "pan_y": -3,
        },
    )
    assert framed_url.endswith("?satellite,10.5000,123.7500,7")
    assert resolve_capture_url({
        "provider": "panahon",
        "url": "https://www.panahon.gov.ph/",
        "framing_decision": cyclone,
    }) == "https://www.panahon.gov.ph/"

    changed = default_config()
    changed["auto_map"]["framing"]["situations"]["cyclone"]["zoom"] = 8
    changed_zoom = determine_map_framing(
        {
            "cyclone_classification": "Typhoon",
            "cyclone_name_local": "TEST",
            "latitude": 18.5,
            "longitude": 130.25,
        },
        image_config=changed,
    )
    assert changed_zoom["zoom"] == 8

    invalid = default_config()
    invalid["auto_map"]["framing"]["default"]["region_id"] = "missing"
    safe = determine_map_framing({}, image_config=invalid)
    assert safe["region_id"] == "philippines"

    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "image_rendering.json"
        old_flat = {
            "fit_mode": "smartfit",
            "target_width": 1080,
            "target_height": 1350,
        }
        path.write_text(json.dumps(old_flat), encoding="utf-8")
        normalized = load_config(path)
        assert normalized["manual_image"]["fit_mode"] == "smartfit"
        assert normalized["auto_map"]["framing"]["enabled"] is True

        full = default_config()
        full["auto_map"]["framing"]["situations"]["cyclone"]["zoom"] = 9
        save_config(full, path)
        set_fit_mode("crop", path)
        preserved = load_config_file(path)
        assert preserved["manual_image"]["fit_mode"] == "crop"
        assert (
            preserved["auto_map"]["framing"]["situations"]["cyclone"]["zoom"]
            == 9
        )

        before = copy.deepcopy(preserved)
        path.write_text('{"version": "broken"}', encoding="utf-8")
        try:
            load_config_file(path)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid image config should be rejected")
        assert before["auto_map"]["framing"]["enabled"] is True

        oversized = Path(temporary_directory) / "oversized.json"
        oversized.write_bytes(b"x" * (100 * 1024 + 1))
        try:
            validate_upload_size(oversized)
        except ValueError:
            pass
        else:
            raise AssertionError("Oversized image config should be rejected")

    print("map framing verification ok")


if __name__ == "__main__":
    main()
