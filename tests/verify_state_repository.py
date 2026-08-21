import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.state_repository import JsonStateRepository


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


if __name__ == "__main__":
    test_restart_recovery()
    test_missing_and_corrupt_state_are_distinct()
    test_atomic_save_keeps_valid_json()
    print("state repository verification ok")
