import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.language_normalization_service as language
from services.forecast_service import parse_forecast_text


def main():
    config = language.load_language_config_file()
    assert language.validate_language_config(config)
    assert len(config["area_phrases"]) == (
        len(language.REQUIRED_REGIONS)
        * len(language.REQUIRED_DIRECTIONS)
    )

    for region in language.REQUIRED_REGIONS:
        for direction in language.REQUIRED_DIRECTIONS:
            phrase = f"the {direction} section of {region}"
            assert phrase in config["area_phrases"], phrase
            assert set(config["area_phrases"][phrase]) >= {
                "body",
                "headline",
                "short",
            }

    phrase = "the western section of Southern Luzon"
    assert language.normalize_area_phrase(phrase) == (
        "kanlurang bahagi ng Timog Luzon"
    )
    assert language.normalize_area_phrase(
        phrase,
        form="headline",
    ) == "Timog Luzon"

    central_philippines = "the central section of the Philippines"
    assert language.normalize_area_phrase(
        central_philippines,
    ) == "gitnang bahagi ng Pilipinas"
    assert language.normalize_area_phrase(
        central_philippines,
        form="headline",
    ) == "Pilipinas"

    assert language.normalize_area_phrase(
        "the northern section of the Philippines"
    ) == "hilagang bahagi ng Pilipinas"
    assert language.normalize_area_phrase(
        "the southern section of the Philippines"
    ) == "katimugang bahagi ng Pilipinas"
    assert language.normalize_area_phrase(
        "Unknown Coastal Area"
    ) == "Unknown Coastal Area"
    assert language.normalize_area_phrase(
        "  THE   WESTERN SECTION OF southern luzon  "
    ) == "kanlurang bahagi ng Timog Luzon"
    assert language.normalize_area_phrase(
        "the western sections of Southern Luzon"
    ) == "kanlurang bahagi ng Timog Luzon"

    forecast = parse_forecast_text(
        "Southwest Monsoon affecting "
        "the western section of Southern Luzon."
    )
    content = forecast["composed_content"]
    assert content["headline"] == "Habagat Nakaaapekto sa Timog Luzon"
    assert "kanlurang bahagi ng Timog Luzon" in content["summary"]
    assert "sa the" not in content["summary"].casefold()

    plural_sections_forecast = parse_forecast_text(
        "Southwest Monsoon affecting the western sections of "
        "Southern Luzon, Visayas and Mindanao."
    )
    plural_summary = plural_sections_forecast["composed_content"]["summary"]
    assert (
        "kanlurang bahagi ng Timog Luzon, Visayas, at Mindanao"
        in plural_summary
    )
    assert "the western sections" not in plural_summary.casefold()

    missing_central = copy.deepcopy(config)
    del missing_central["area_phrases"][
        "the central section of Mindanao"
    ]
    try:
        language.validate_language_config(missing_central)
    except ValueError as error:
        assert "central section of Mindanao" in str(error)
    else:
        raise AssertionError("Missing central variant should fail")

    original_path = language.CONFIG_PATH
    original_backup_dir = language.BACKUP_DIR
    original_cache = language._config_cache
    original_loaded = language._last_loaded
    original_error = language._last_validation_error

    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            active_path = root / "language.json"
            language.CONFIG_PATH = active_path
            language.BACKUP_DIR = root / "backups"
            language._config_cache = None

            fallback = language.get_language_config()
            assert fallback["area_phrases"] == {}
            assert language.normalize_area_phrase(
                phrase,
                config=fallback,
            ) == phrase

            active_path.write_text(
                json.dumps(config),
                encoding="utf-8",
            )
            loaded = language.reload_language_config()
            assert loaded["area_phrases"]

            invalid_upload = root / "invalid.json"
            invalid_upload.write_text(
                json.dumps(missing_central),
                encoding="utf-8",
            )
            before = active_path.read_text(encoding="utf-8")
            try:
                language.replace_language_config_from_file(
                    invalid_upload
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid upload should fail")
            assert active_path.read_text(encoding="utf-8") == before

            active_path.write_text('{"version": "broken"}')
            try:
                language.reload_language_config()
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid reload should fail")
            assert language.get_language_config() == loaded
    finally:
        language.CONFIG_PATH = original_path
        language.BACKUP_DIR = original_backup_dir
        language._config_cache = original_cache
        language._last_loaded = original_loaded
        language._last_validation_error = original_error

    print("language normalization verification ok")


if __name__ == "__main__":
    main()
