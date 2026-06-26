import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.forecast_parser import parse_pagasa_forecast_text
import services.caption_template_service as templates


VALID_TEMPLATE = {
    "version": "test",
    "language": "fil",
    "provider": "PAGASA",
    "templates": {
        "cyclone_location": "{cyclone_classification} {cyclone_name_local_title} {location_text}",
        "cyclone_intensity": "{maximum_sustained_winds_kmh} {gustiness_kmh}",
        "cyclone_movement": "{movement_direction_fil} {movement_speed_kmh}",
        "affected_system": "{affected_weather_system_fil} {affected_areas_text}",
        "source_line": "Forecast: PAGASA | pagasa.dost.gov.ph",
    },
    "translations": {
        "weather_systems": {
            "southwest monsoon": "Habagat",
        },
        "movement_directions": {
            "north northwestward": "pahilagang-kanluran",
        },
    },
}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def expect_failure(fn, expected_text):
    try:
        fn()
    except Exception as error:
        assert expected_text in str(error), str(error)
        return

    raise AssertionError(f"Expected failure containing: {expected_text}")


def main():
    original_template_path = templates.TEMPLATE_PATH
    original_backup_dir = templates.BACKUP_DIR
    original_cache = templates._template_cache
    original_error = templates._last_validation_error
    original_loaded = templates._last_loaded

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            good_path = tmp / "good.json"
            missing_path = tmp / "missing.json"
            unknown_path = tmp / "unknown.json"
            oversized_path = tmp / "oversized.json"
            bad_reload_path = tmp / "bad_reload.json"

            write_json(good_path, VALID_TEMPLATE)
            templates.validate_template_file(good_path)

            missing_template = json.loads(json.dumps(VALID_TEMPLATE))
            del missing_template["templates"]["cyclone_intensity"]
            write_json(missing_path, missing_template)
            expect_failure(
                lambda: templates.validate_template_file(missing_path),
                "Missing required templates",
            )

            unknown_template = json.loads(json.dumps(VALID_TEMPLATE))
            unknown_template["templates"]["cyclone_location"] = "{bad_placeholder}"
            write_json(unknown_path, unknown_template)
            expect_failure(
                lambda: templates.validate_template_file(unknown_path),
                "unknown placeholders",
            )

            oversized_path.write_text("x" * (templates.MAX_TEMPLATE_UPLOAD_BYTES + 1))
            expect_failure(
                lambda: templates.validate_template_upload_size(oversized_path),
                "Template upload rejected: file too large.",
            )

            templates.TEMPLATE_PATH = good_path
            templates.BACKUP_DIR = tmp / "backups"
            templates._template_cache = None
            templates.reload_templates()
            assert templates.get_template()["version"] == "test"

            bad_reload_path.write_text("{bad json")
            templates.TEMPLATE_PATH = bad_reload_path
            expect_failure(templates.reload_templates, "Expecting property name")
            assert templates.get_template()["version"] == "test"

            malformed = parse_pagasa_forecast_text("Southwest Monsoon affecting Luzon.")
            assert malformed["cyclone_name_local"] is None
            assert malformed["affected_weather_system"] == "Southwest Monsoon"

            print("template guardrails verification ok")

    finally:
        templates.TEMPLATE_PATH = original_template_path
        templates.BACKUP_DIR = original_backup_dir
        templates._template_cache = original_cache
        templates._last_validation_error = original_error
        templates._last_loaded = original_loaded


if __name__ == "__main__":
    main()
