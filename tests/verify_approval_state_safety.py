import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage.approval_store as approval_store


def sample_state():
    return {
        "current": {
            "job_id": "state-safety-job",
            "status": "pending",
        },
        "history": [],
    }


def main():
    original_state_file = approval_store.STATE_FILE
    original_replace = approval_store.os.replace

    try:
        with tempfile.TemporaryDirectory() as temporary_dir:
            state_file = Path(temporary_dir) / "approval_state.json"
            approval_store.STATE_FILE = state_file

            approval_store.save_state(sample_state())
            loaded = approval_store.load_state()
            assert loaded["current"]["job_id"] == "state-safety-job"
            assert json.loads(state_file.read_text(encoding="utf-8")) == loaded
            assert not list(state_file.parent.glob("*.tmp"))

            original_content = state_file.read_text(encoding="utf-8")

            def fail_replace(source, destination):
                raise OSError("simulated replace failure")

            approval_store.os.replace = fail_replace
            try:
                approval_store.save_state({
                    "current": None,
                    "history": [],
                })
            except OSError:
                pass
            else:
                raise AssertionError("Failed atomic replace must raise")
            assert state_file.read_text(encoding="utf-8") == original_content
            approval_store.os.replace = original_replace

            state_file.write_text("{incomplete", encoding="utf-8")
            try:
                approval_store.load_state()
            except RuntimeError as error:
                assert "could not be read safely" in str(error)
            else:
                raise AssertionError(
                    "Malformed state must not become an empty state"
                )

            approval_store.save_state(sample_state())

            def update_field(name):
                for value in range(20):
                    approval_store.update_current_job(
                        {name: value},
                        preserve_status=True,
                    )

            threads = [
                threading.Thread(target=update_field, args=("worker_a",)),
                threading.Thread(target=update_field, args=("worker_b",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            concurrent = approval_store.load_state()["current"]
            assert concurrent["job_id"] == "state-safety-job"
            assert concurrent["worker_a"] == 19
            assert concurrent["worker_b"] == 19
            assert concurrent["status"] == "pending"

    finally:
        approval_store.os.replace = original_replace
        approval_store.STATE_FILE = original_state_file

    print("approval state safety verification ok")


if __name__ == "__main__":
    main()
