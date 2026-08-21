import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.state_repository import (
    JsonStateRepository,
    RedisStateRepository,
    get_state_backend_name,
    get_state_repository,
)


def test_restart_recovery():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        repository.save({"status": "approved", "retry": 2, "provenance": {"mode": "templated"}})
        restarted = JsonStateRepository(path)
        assert restarted.load(lambda: {})["status"] == "approved"
        assert restarted.load(lambda: {})["retry"] == 2


def test_missing_and_corrupt_state_are_distinct():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        assert repository.load(lambda: {"empty": True}) == {"empty": True}
        path.write_text("{not-json", encoding="utf-8")
        try:
            repository.load(dict)
        except RuntimeError as error:
            assert "not replaced" in str(error)
        else:
            raise AssertionError("Corrupt state must not become empty state")


def test_atomic_save_keeps_valid_json():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        repository.save({"value": "persisted"})
        assert json.loads(path.read_text(encoding="utf-8")) == {"value": "persisted"}


class FakeRedisStateRepository(RedisStateRepository):
    values = {}

    def _command(self, *parts):
        command = parts[0]
        if command == "GET":
            return self.values.get(parts[1])
        if command == "SET":
            self.values[parts[1]] = parts[2]
            return "OK"
        raise AssertionError(command)


def test_external_repository_round_trip_and_namespace():
    first = FakeRedisStateRepository("redis://localhost", "weatherwatch:approval_state")
    second = FakeRedisStateRepository("redis://localhost", "weatherwatch:facebook_token_state")
    first.save({"current": {"status": "approved"}, "history": []})
    assert first.load(dict)["current"]["status"] == "approved"
    assert second.load(lambda: {"missing": True}) == {"missing": True}


def test_backend_selection_is_explicit():
    original = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    try:
        os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        assert get_state_backend_name() == "filesystem"
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "unknown"
        try:
            get_state_backend_name()
        except ValueError as error:
            assert "Unsupported" in str(error)
        else:
            raise AssertionError("Unknown backend must fail clearly")
    finally:
        if original is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original


def test_redis_backend_requires_url():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_url = os.environ.get("WEATHERWATCH_REDIS_URL")
    try:
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "redis"
        os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        try:
            get_state_repository(Path("/tmp/p15-state.json"), state_key="test")
        except ValueError as error:
            assert "WEATHERWATCH_REDIS_URL" in str(error)
        else:
            raise AssertionError("Redis backend without URL must fail clearly")
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_url is None:
            os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        else:
            os.environ["WEATHERWATCH_REDIS_URL"] = original_url


if __name__ == "__main__":
    test_restart_recovery()
    test_missing_and_corrupt_state_are_distinct()
    test_atomic_save_keeps_valid_json()
    test_external_repository_round_trip_and_namespace()
    test_backend_selection_is_explicit()
    test_redis_backend_requires_url()
    print("state repository verification ok")
