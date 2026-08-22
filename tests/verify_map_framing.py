import copy
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.image_rendering_service import (
    crop,
    default_config,
    load_config,
    load_config_file,
    save_config,
    set_fit_mode,
    smartfit,
    stretch,
    validate_upload_size,
)
from services.capture_service import apply_windy_framing
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


def assert_area_region(areas, expected_region, image_config=None):
    decision = determine_map_framing(
        {
            "affected_weather_system": "Southwest Monsoon",
            "affected_areas": areas,
        },
        "Southwest Monsoon affecting " + ", ".join(areas) + ".",
        image_config=image_config,
    )
    assert decision["region_id"] == expected_region
    assert decision["matched_region_id"] == expected_region
    assert decision["source"] == "affected_area"
    assert decision["matched_areas"] == areas
    assert decision["strategy"] == "region"
    return decision


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
    assert_area_region(["Mindanao"], "mindanao")
    assert_area_region(["Visayas"], "visayas")
    assert_area_region(["Luzon"], "luzon")
    southern_luzon = assert_area_region(
        ["Southern Luzon"],
        "southern_luzon",
    )
    assert southern_luzon["matched_regions"] == ["southern_luzon"]
    assert southern_luzon["resolved_parent_groups"] == ["luzon"]
    assert southern_luzon["fallback_used"] is False

    southern_visayas = assert_area_region(
        ["Southern Visayas"],
        "visayas",
    )
    assert southern_visayas["matched_regions"] == ["southern_visayas"]
    assert southern_visayas["resolved_parent_groups"] == ["visayas"]
    assert southern_visayas["fallback_used"] is True
    assert "using parent group visayas" in southern_visayas["fallback_reason"]

    southern_mindanao = assert_area_region(
        ["Timog Mindanao"],
        "mindanao",
    )
    assert southern_mindanao["matched_regions"] == ["southern_mindanao"]
    assert southern_mindanao["resolved_parent_groups"] == ["mindanao"]
    assert southern_mindanao["fallback_used"] is True
    assert "using parent group mindanao" in southern_mindanao["fallback_reason"]

    assert_area_region(["Luzon", "Visayas"], "luzon_visayas")
    assert_area_region(["Visayas", "Mindanao"], "visayas_mindanao")
    assert_area_region(["Luzon", "Mindanao"], "philippines")
    assert_area_region(
        ["kanlurang bahagi ng Timog Luzon", "Visayas"],
        "luzon_visayas",
    )
    all_island_groups = assert_area_region(
        ["kanlurang bahagi ng Timog Luzon", "Visayas", "Mindanao"],
        "philippines",
    )
    assert all_island_groups["zoom"] == 5
    assert_area_region(["the Philippines"], "philippines")
    assert_area_region(["Timog Luzon"], "southern_luzon")

    dedicated_config = default_config()
    dedicated_config["auto_map"]["framing"]["regions"][
        "southern_visayas"
    ].update({
        "center_lat": 9.5,
        "center_lon": 123.5,
        "zoom": 7,
        "pan_x": 0.5,
        "pan_y": -0.25,
    })
    dedicated_southern_visayas = assert_area_region(
        ["Timog Visayas"],
        "southern_visayas",
        image_config=dedicated_config,
    )
    assert dedicated_southern_visayas["zoom"] == 7
    assert dedicated_southern_visayas["pan_x"] == 0.5
    assert dedicated_southern_visayas["pan_y"] == -0.25
    assert dedicated_southern_visayas["fallback_used"] is False

    normalized_forms = determine_map_framing(
        {
            "affected_weather_system": "Southwest Monsoon",
            "affected_areas_headline": ["Timog Luzon", "Visayas", "Mindanao"],
            "affected_areas_short": ["Timog Luzon", "Visayas", "Mindanao"],
            "affected_areas": [
                "kanlurang bahagi ng Timog Luzon",
                "Visayas",
                "Mindanao",
            ],
            "affected_areas_original": [
                "the western sections of Southern Luzon",
                "Visayas",
                "Mindanao",
            ],
        },
        "Southwest Monsoon affecting the western sections of "
        "Southern Luzon, Visayas and Mindanao.",
    )
    assert normalized_forms["region_id"] == "philippines"
    assert normalized_forms["matched_regions"] == [
        "southern_luzon",
        "visayas",
        "mindanao",
    ]
    assert normalized_forms["matched_areas"][0] == "Timog Luzon"

    mindanao_habagat = assert_area_region(["Mindanao"], "mindanao")
    assert mindanao_habagat["situation_id"] == "monsoon_southwest"
    assert mindanao_habagat["reason"] == "Affected area framing matched mindanao"

    fallback_to_situation = determine_map_framing(
        {
            "affected_weather_system": "Southwest Monsoon",
            "affected_areas": ["Unknown Area"],
        },
        "Southwest Monsoon affecting Unknown Area.",
    )
    assert fallback_to_situation["region_id"] == "luzon_visayas"
    assert fallback_to_situation["source"] == "weather_system"

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

    area_config = default_config()
    area_config["auto_map"]["framing"]["regions"]["mindanao"]["zoom"] = 9
    area_config["auto_map"]["framing"]["regions"]["mindanao"]["pan_x"] = 1.25
    area_config["auto_map"]["framing"]["regions"]["mindanao"]["pan_y"] = -0.5
    changed_area = assert_area_region(
        ["Mindanao"],
        "mindanao",
        image_config=area_config,
    )
    assert changed_area["zoom"] == 9
    assert changed_area["pan_x"] == 1.25
    assert changed_area["pan_y"] == -0.5

    source = Image.new("RGB", (1600, 900), color="navy")
    for renderer in (stretch, smartfit, crop):
        rendered = renderer(source)
        assert rendered.size == (1080, 1350)

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

        legacy = default_config()
        legacy_framing = legacy["auto_map"]["framing"]
        legacy_aliases = {}
        for region_id, region in legacy_framing["regions"].items():
            legacy_aliases[region_id] = region.pop("aliases")
            region.pop("parent_group")
        for region_id in (
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
        ):
            legacy_framing["regions"].pop(region_id)
            legacy_aliases.pop(region_id)
        legacy_framing["area_routing"] = {
            "enabled": True,
            "aliases": legacy_aliases,
            "combinations": {
                "luzon+visayas": "luzon_visayas",
            },
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")
        migrated = load_config_file(path)
        assert migrated["auto_map"]["framing"]["regions"][
            "southern_visayas"
        ]["parent_group"] == "visayas"

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
