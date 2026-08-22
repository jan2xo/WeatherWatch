"""Validated, provider-neutral AI editorial configuration.

This module stores no credentials and performs no provider/network calls.
Provider adapters may consume the validated configuration in a later lane.
"""

import copy
import json
import os
import re
from pathlib import Path


CONFIG_PATH = Path("config/ai_editorial.json")
SUPPORTED_MODES = {"templated", "ai_assisted", "automatic"}
MAX_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 10
PROVIDER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def provider_runtime_prefix(name):
    return f"WEATHERWATCH_AI_{name.upper()}"


def _parse_boolean_override(name, value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def apply_runtime_provider_overrides(config, environ=None):
    """Overlay owner-controlled provider switches without mutating JSON defaults."""

    environment = os.environ if environ is None else environ
    effective = copy.deepcopy(config)
    if "WEATHERWATCH_EDITORIAL_MODE" in environment:
        effective["mode"] = str(environment["WEATHERWATCH_EDITORIAL_MODE"]).strip()
    for provider in effective.get("providers", ()):
        name = provider.get("name")
        if not isinstance(name, str) or not name:
            continue
        prefix = provider_runtime_prefix(name)
        enabled_name = f"{prefix}_ENABLED"
        model_name = f"{prefix}_MODEL"
        timeout_name = f"{prefix}_TIMEOUT_SECONDS"

        if enabled_name in environment:
            provider["enabled"] = _parse_boolean_override(
                enabled_name, environment[enabled_name]
            )
        if model_name in environment:
            provider["model"] = str(environment[model_name]).strip()
        if timeout_name in environment:
            try:
                provider["timeout_seconds"] = int(
                    str(environment[timeout_name]).strip()
                )
            except ValueError as error:
                raise ValueError(f"{timeout_name} must be an integer.") from error
    return effective


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
        if not isinstance(name, str) or not PROVIDER_NAME_PATTERN.fullmatch(name):
            raise ValueError("Each AI provider requires a safe lowercase name.")
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

        endpoint = provider.get("endpoint", "")
        if not isinstance(endpoint, str):
            raise ValueError("AI provider endpoint must be a string.")

        credential_reference = provider.get("credential_reference", "")
        if not isinstance(credential_reference, str) or (
            credential_reference
            and not ENVIRONMENT_NAME_PATTERN.fullmatch(credential_reference)
        ):
            raise ValueError("AI provider credential_reference must be a safe environment name.")
        if enabled and not credential_reference:
            raise ValueError("Enabled AI providers require a credential_reference.")

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


def get_ai_config(path=CONFIG_PATH, environ=None):
    config = load_config_file(path)
    config = apply_runtime_provider_overrides(config, environ=environ)
    validate_ai_config(config)
    return config


def get_ai_config_status(path=CONFIG_PATH, environ=None):
    try:
        from services.ai_provider_adapters import get_provider_runtime_status

        config = get_ai_config(path, environ=environ)
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
                    **get_provider_runtime_status(provider, environ=environ),
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


def get_enabled_provider_configs(path=CONFIG_PATH, environ=None):
    config = get_ai_config(path, environ=environ)
    enabled = tuple(
        provider
        for provider in sorted(config["providers"], key=lambda item: item["priority"])
        if provider["enabled"]
    )
    if not enabled:
        return ()
    if not config["fallback"]["enabled"]:
        return enabled[:1]
    return enabled[:config["fallback"]["max_attempts"]]
