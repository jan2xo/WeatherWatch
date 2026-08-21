import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_config_service


def verify_valid_config():
    config = ai_config_service.load_config_file()
    assert ai_config_service.validate_ai_config(config)
    assert config["mode"] == "templated"


def verify_enabled_provider_requires_model():
    config = copy.deepcopy(ai_config_service.load_config_file())
    config["providers"][0]["enabled"] = True
    try:
        ai_config_service.validate_ai_config(config)
    except ValueError as error:
        assert "selected model" in str(error)
    else:
        raise AssertionError("Enabled provider without model must fail")


def verify_duplicate_priority_rejected():
    config = copy.deepcopy(ai_config_service.load_config_file())
    config["providers"][1]["priority"] = config["providers"][0]["priority"]
    try:
        ai_config_service.validate_ai_config(config)
    except ValueError as error:
        assert "priorities" in str(error)
    else:
        raise AssertionError("Duplicate priorities must fail")


def verify_invalid_mode_rejected():
    config = copy.deepcopy(ai_config_service.load_config_file())
    config["mode"] = "unsupported"
    try:
        ai_config_service.validate_ai_config(config)
    except ValueError as error:
        assert "mode" in str(error)
    else:
        raise AssertionError("Unsupported mode must fail")


if __name__ == "__main__":
    verify_valid_config()
    verify_enabled_provider_requires_model()
    verify_duplicate_priority_rejected()
    verify_invalid_mode_rejected()
    print("AI configuration verification ok")
