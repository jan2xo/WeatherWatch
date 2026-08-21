"""Validated, provider-neutral AI editorial configuration.

This module stores no credentials and performs no provider/network calls.
Provider adapters may consume the validated configuration in a later lane.
"""

import json
from pathlib import Path


CONFIG_PATH = Path("config/ai_editorial.json")
SUPPORTED_MODES = {"templated", "ai_assisted", "automatic"}
MAX_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 10


def load_config_file(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_ai_config(config):
    if not isinstance(config, dict):
        raise ValueError("AI configuration must be an object.")

    if config.get("version") != "1.0":
        raise ValueError("AI configuration version must be 1.0.")

    if config.get("mode") not in SUPPORTED_MODES:
        raise ValueError("AI configuration mode is unsupported.")

    providers = config.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError("AI configuration requires a providers list.")

    names = set()
    priorities = set()
    for provider in providers:
        if not isinstance(provider, dict):
            raise ValueError("Each AI provider configuration must be an object.")

        name = provider.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each AI provider requires a name.")
        if name in names:
            raise ValueError("AI provider names must be unique.")
        names.add(name)

        priority = provider.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise ValueError("AI provider priority must be a non-negative integer.")
        if priority in priorities:
            raise ValueError("AI provider priorities must be unique.")
        priorities.add(priority)

        enabled = provider.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("AI provider enabled must be boolean.")

        model = provider.get("model")
        if not isinstance(model, str):
            raise ValueError("AI provider model must be a string.")
        if enabled and not model.strip():
            raise ValueError("Enabled AI providers require a selected model.")

        timeout = provider.get("timeout_seconds")
        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or timeout < 1
            or timeout > MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("AI provider timeout_seconds is outside the safe range.")

    fallback = config.get("fallback")
    if not isinstance(fallback, dict):
        raise ValueError("AI configuration requires fallback settings.")
    if not isinstance(fallback.get("enabled"), bool):
        raise ValueError("AI fallback enabled must be boolean.")
    attempts = fallback.get("max_attempts")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= MAX_ATTEMPTS:
        raise ValueError("AI fallback max_attempts is outside the safe range.")

    return True


def get_ai_config(path=CONFIG_PATH):
    config = load_config_file(path)
    validate_ai_config(config)
    return config


def get_ai_config_status(path=CONFIG_PATH):
    try:
        config = get_ai_config(path)
        providers = sorted(config["providers"], key=lambda provider: provider["priority"])
        return {
            "config_path": str(path),
            "version": config["version"],
            "mode": config["mode"],
            "fallback_enabled": config["fallback"]["enabled"],
            "max_attempts": config["fallback"]["max_attempts"],
            "validation_status": "valid",
            "last_validation_error": None,
            "providers": [
                {
                    "name": provider["name"],
                    "enabled": provider["enabled"],
                    "priority": provider["priority"],
                    "model": provider["model"] or None,
                    "timeout_seconds": provider["timeout_seconds"],
                }
                for provider in providers
            ],
        }
    except Exception as error:
        return {
            "config_path": str(path),
            "version": None,
            "mode": None,
            "fallback_enabled": None,
            "max_attempts": None,
            "validation_status": "invalid",
            "last_validation_error": str(error),
            "providers": [],
        }
