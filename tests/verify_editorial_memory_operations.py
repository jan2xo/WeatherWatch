import copy
import importlib
import json
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import ai_config_service
from services import editorial_memory_service as memory
from services.ai_provider_adapters import (
    ProviderRequestError,
    build_provider_from_config,
    get_provider_runtime_status,
    resolve_provider_endpoint,
)
from tools.editorial_memory import main as memory_command


def valid_memory(memory_id="rain-cagayan-001"):
    return {
        "memory_id": memory_id,
        "approved": True,
        "created_at": "2026-08-22T12:00:00+08:00",
        "updated_at": "2026-08-22T12:30:00+08:00",
        "headline": "Approved headline",
        "caption": "Approved caption",
        "tags": ["rain", "cagayan"],
        "category": "rain_advisory",
        "locations": ["Cagayan"],
        "tone": "calm",
        "source_type": "owner_curated",
    }


def verify_owner_provider_overrides():
    base = ai_config_service.load_config_file()
    original = copy.deepcopy(base)
    test_key = "synthetic" + "-only"
    environment = {
        "WEATHERWATCH_EDITORIAL_MODE": "automatic",
        "WEATHERWATCH_AI_OPENROUTER_ENABLED": "true",
        "WEATHERWATCH_AI_OPENROUTER_MODEL": "owner-selected-model",
        "WEATHERWATCH_AI_OPENROUTER_TIMEOUT_SECONDS": "45",
        "OPENROUTER_API_KEY": test_key,
    }
    effective = ai_config_service.apply_runtime_provider_overrides(
        base, environ=environment
    )
    assert base == original
    assert effective["mode"] == "automatic"
    assert effective["providers"][0]["enabled"] is True
    assert effective["providers"][0]["model"] == "owner-selected-model"
    assert effective["providers"][0]["timeout_seconds"] == 45
    assert ai_config_service.validate_ai_config(effective)

    status = ai_config_service.get_ai_config_status(environ=environment)
    openrouter = status["providers"][0]
    assert openrouter["runtime_ready"] is True
    assert openrouter["endpoint_configured"] is True
    assert openrouter["key_configured"] is True
    assert test_key not in json.dumps(status)

    try:
        ai_config_service.apply_runtime_provider_overrides(
            base,
            environ={"WEATHERWATCH_AI_OPENROUTER_ENABLED": "perhaps"},
        )
    except ValueError as error:
        assert "boolean" in str(error)
    else:
        raise AssertionError("Invalid provider enabled override must fail")


def verify_ordered_fallback_policy():
    config = ai_config_service.load_config_file()
    for index, provider in enumerate(config["providers"]):
        provider["enabled"] = True
        provider["model"] = f"owner-model-{index}"
    config["fallback"]["max_attempts"] = 2

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ai.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        enabled = ai_config_service.get_enabled_provider_configs(path, environ={})
        assert [item["name"] for item in enabled] == ["openrouter", "provider_2"]

        config["fallback"]["enabled"] = False
        path.write_text(json.dumps(config), encoding="utf-8")
        enabled = ai_config_service.get_enabled_provider_configs(path, environ={})
        assert [item["name"] for item in enabled] == ["openrouter"]


def verify_endpoint_and_key_boundaries():
    provider = {
        "name": "provider_2",
        "enabled": True,
        "model": "owner-model",
        "timeout_seconds": 20,
        "credential_reference": "AI_PROVIDER_2_API_KEY",
    }
    test_key = "synthetic" + "-key"
    environment = {
        "AI_PROVIDER_2_BASE_URL": "https://provider.example/v1",
        "AI_PROVIDER_2_API_KEY": test_key,
    }
    assert resolve_provider_endpoint(provider, environ=environment) == (
        "https://provider.example/v1"
    )
    built = build_provider_from_config(provider, environ=environment)
    assert built.base_url == "https://provider.example/v1"
    assert built.api_key_env == "AI_PROVIDER_2_API_KEY"

    status = get_provider_runtime_status(provider, environ={})
    assert status["endpoint_configured"] is False
    assert status["key_configured"] is False
    assert status["runtime_ready"] is False

    unsafe = {**provider, "endpoint": "https://user:password@provider.example/v1"}
    try:
        resolve_provider_endpoint(
            unsafe,
            environ={"AI_PROVIDER_2_API_KEY": test_key},
        )
    except ProviderRequestError as error:
        assert "invalid" in str(error)
        assert "password" not in str(error)
    else:
        raise AssertionError("Credential-bearing provider endpoint must fail")


def verify_strict_memory_validation_and_cli():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "editorial_memory.json"
        path.write_text(json.dumps([valid_memory()]), encoding="utf-8")
        result = memory.validate_editorial_memory_operations(path)
        assert result["items"] == 1
        assert result["approved_items"] == 1

        output = StringIO()
        with redirect_stdout(output):
            assert memory_command(["validate", str(path)]) == 0
        assert json.loads(output.getvalue())["validation_status"] == "valid"

        output = StringIO()
        with redirect_stdout(output):
            assert memory_command(["schema"]) == 0
        schema = json.loads(output.getvalue())
        assert "created_at" in schema["required_fields"]
        assert schema["retrieval_limit"] == memory.MAX_RETRIEVAL_LIMIT
        assert "canonical structured weather facts" in schema["weather_authority"]

        duplicate = [valid_memory(), valid_memory()]
        path.write_text(json.dumps(duplicate), encoding="utf-8")
        try:
            memory.validate_editorial_memory_operations(path)
        except ValueError as error:
            assert "unique" in str(error)
        else:
            raise AssertionError("Duplicate memory IDs must fail")

        invalid = valid_memory("Upper Case")
        invalid["updated_at"] = "2026-08-21T12:00:00+08:00"
        path.write_text(json.dumps([invalid]), encoding="utf-8")
        try:
            memory.validate_editorial_memory_operations(path)
        except ValueError as error:
            assert "memory_id" in str(error)
        else:
            raise AssertionError("Unstable memory ID must fail")

        invalid = valid_memory()
        invalid["created_at"] = "2026-08-22T12:00:00"
        path.write_text(json.dumps([invalid]), encoding="utf-8")
        try:
            memory.validate_editorial_memory_operations(path)
        except ValueError as error:
            assert "timezone" in str(error)
        else:
            raise AssertionError("Naive memory timestamp must fail")


def verify_runtime_seed_and_bounded_retrieval():
    original_root = os.environ.get("WEATHERWATCH_RUNTIME_ROOT")
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "config" / "editorial_memory.json"
        try:
            os.environ["WEATHERWATCH_RUNTIME_ROOT"] = directory
            importlib.reload(memory)
            assert memory.DEFAULT_MEMORY_PATH == target
            result = memory.validate_editorial_memory_operations(target)
            assert result["items"] == 0
            assert target.read_text(encoding="utf-8").strip() == "[]"
        finally:
            if original_root is None:
                os.environ.pop("WEATHERWATCH_RUNTIME_ROOT", None)
            else:
                os.environ["WEATHERWATCH_RUNTIME_ROOT"] = original_root
            importlib.reload(memory)

    try:
        memory.retrieve_relevant_memory([], limit=memory.MAX_RETRIEVAL_LIMIT + 1)
    except ValueError as error:
        assert "between" in str(error)
    else:
        raise AssertionError("Unbounded memory retrieval must fail")


def main():
    verify_owner_provider_overrides()
    verify_ordered_fallback_policy()
    verify_endpoint_and_key_boundaries()
    verify_strict_memory_validation_and_cli()
    verify_runtime_seed_and_bounded_retrieval()
    print("editorial memory operations verification ok")


if __name__ == "__main__":
    main()
