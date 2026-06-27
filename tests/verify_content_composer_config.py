import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.content_composer_config_service as config_service
from services.content_composer_service import compose_weather_content


def monsoon_data(system):
    return {
        "affected_weather_system": system,
        "affected_areas": ["Luzon", "Visayas"],
    }


def verify_valid_and_missing_keys():
    valid = config_service.default_composer_config()
    assert config_service.validate_composer_config(valid)

    invalid = copy.deepcopy(valid)
    del invalid["composer"]["cyclone"]

    try:
        config_service.validate_composer_config(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing composer.cyclone should fail")


def verify_aliases():
    habagat = compose_weather_content(
        "Habagat affecting Luzon and Visayas.",
        monsoon_data("Habagat"),
    )
    combined_name = compose_weather_content(
        "Southwest Monsoon (Habagat) affecting Luzon and Visayas.",
        monsoon_data("Southwest Monsoon (Habagat)"),
    )

    assert habagat["content_type"] == "monsoon_update"
    assert combined_name["content_type"] == "monsoon_update"


def verify_configured_wording():
    config = config_service.default_composer_config()
    config["composer"]["default_source_line"] = "Forecast: TEST"
    system = config["composer"]["monsoon"]["systems"]["Southwest Monsoon"]
    system["headline_template"] = "{display_name}: Apektado ang {areas_text}"
    system["summary_template"] = (
        "Umiiral ang {display_name} sa {areas_text}."
    )

    content = compose_weather_content(
        "Southwest Monsoon affecting Luzon and Visayas.",
        monsoon_data("Southwest Monsoon"),
        composer_config=config,
    )

    assert content["headline"] == "Habagat: Apektado ang Luzon at Visayas"
    assert content["summary"] == "Umiiral ang Habagat sa Luzon at Visayas."
    assert content["source_line"] == "Forecast: TEST"


def verify_last_known_good():
    original_path = config_service.CONFIG_PATH
    original_cache = config_service._config_cache
    original_loaded = config_service._last_loaded
    original_error = config_service._last_validation_error

    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "content_composer.json"
            good = config_service.default_composer_config()
            path.write_text(json.dumps(good), encoding="utf-8")

            config_service.CONFIG_PATH = path
            config_service._config_cache = None
            loaded = config_service.reload_composer_config()
            assert loaded["version"] == "1.0"

            path.write_text('{"version": "broken"}', encoding="utf-8")

            try:
                config_service.reload_composer_config()
            except ValueError:
                pass
            else:
                raise AssertionError("Malformed reload should fail")

            preserved = config_service.get_composer_config()
            assert preserved == loaded

            content = compose_weather_content(
                "Habagat affecting Luzon and Visayas.",
                monsoon_data("Habagat"),
            )
            assert content["content_type"] == "monsoon_update"
    finally:
        config_service.CONFIG_PATH = original_path
        config_service._config_cache = original_cache
        config_service._last_loaded = original_loaded
        config_service._last_validation_error = original_error


def main():
    verify_valid_and_missing_keys()
    verify_aliases()
    verify_configured_wording()
    verify_last_known_good()
    print("content composer config verification ok")


if __name__ == "__main__":
    main()
