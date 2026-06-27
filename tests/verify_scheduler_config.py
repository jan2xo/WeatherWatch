import copy
import json
import sys
import tempfile
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.scheduler import register_scheduler_jobs
import core.scheduler as scheduler_runtime
import services.scheduler_config_service as scheduler_config


def expect_failure(callback, expected):
    try:
        callback()
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError(f"Expected failure containing: {expected}")


def main():
    valid = scheduler_config.default_scheduler_config()
    assert scheduler_config.validate_scheduler_config(valid)

    invalid_time = copy.deepcopy(valid)
    invalid_time["jobs"][0]["time"] = "25:61"
    expect_failure(
        lambda: scheduler_config.validate_scheduler_config(invalid_time),
        "HH:MM",
    )

    duplicate = copy.deepcopy(valid)
    duplicate["jobs"][1]["id"] = duplicate["jobs"][0]["id"]
    expect_failure(
        lambda: scheduler_config.validate_scheduler_config(duplicate),
        "Duplicate",
    )

    test_scheduler = BackgroundScheduler()
    disabled = copy.deepcopy(valid)
    disabled["enabled"] = False
    assert register_scheduler_jobs(
        disabled,
        lambda: None,
        test_scheduler,
    ) == []
    assert test_scheduler.get_jobs() == []

    one_disabled_job = copy.deepcopy(valid)
    one_disabled_job["jobs"][0]["enabled"] = False
    registered = register_scheduler_jobs(
        one_disabled_job,
        lambda: None,
        test_scheduler,
    )
    assert "morning_update" not in registered
    assert len(registered) == 2

    original_get_current_job = scheduler_runtime.get_current_job
    original_reject_current_job = scheduler_runtime.reject_current_job
    events = []
    try:
        scheduler_runtime.get_current_job = lambda: {
            "job_id": "pending-test",
            "status": "pending",
        }
        scheduler_runtime.reject_current_job = lambda: events.append(
            "rejected"
        )
        result = scheduler_runtime.run_weather_update_job(
            valid["jobs"][0],
            lambda: events.append("updated") or "updated",
            valid["pending_job_policy"],
        )
        assert result == "updated"
        assert events == ["rejected", "updated"]

        events.clear()
        scheduler_runtime.get_current_job = lambda: {
            "job_id": "approved-test",
            "status": "approved",
        }
        result = scheduler_runtime.run_weather_update_job(
            valid["jobs"][0],
            lambda: events.append("updated"),
            valid["pending_job_policy"],
        )
        assert result["skipped"] is True
        assert events == []
    finally:
        scheduler_runtime.get_current_job = original_get_current_job
        scheduler_runtime.reject_current_job = original_reject_current_job

    original_path = scheduler_config.CONFIG_PATH
    original_backup_dir = scheduler_config.BACKUP_DIR
    original_cache = scheduler_config._config_cache
    original_loaded = scheduler_config._last_loaded
    original_error = scheduler_config._last_validation_error

    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            active_path = root / "scheduler.json"
            scheduler_config.CONFIG_PATH = active_path
            scheduler_config.BACKUP_DIR = root / "backups"
            scheduler_config._config_cache = None

            missing_default = scheduler_config.get_scheduler_config()
            assert missing_default["timezone"] == "Asia/Manila"

            active_path.write_text(json.dumps(valid), encoding="utf-8")
            loaded = scheduler_config.reload_scheduler_config()
            assert loaded == valid

            active_path.write_text(
                json.dumps({"version": "broken"}),
                encoding="utf-8",
            )
            try:
                scheduler_config.reload_scheduler_config()
            except ValueError:
                pass
            else:
                raise AssertionError("Bad reload should fail")
            assert scheduler_config.get_scheduler_config() == loaded

            active_path.write_text(json.dumps(valid), encoding="utf-8")
            scheduler_config.reload_scheduler_config()
            invalid_upload = root / "invalid-upload.json"
            invalid_upload.write_text(
                json.dumps(invalid_time),
                encoding="utf-8",
            )
            before = active_path.read_text(encoding="utf-8")
            try:
                scheduler_config.replace_scheduler_config_from_file(
                    invalid_upload
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid upload should fail")
            assert active_path.read_text(encoding="utf-8") == before
    finally:
        scheduler_config.CONFIG_PATH = original_path
        scheduler_config.BACKUP_DIR = original_backup_dir
        scheduler_config._config_cache = original_cache
        scheduler_config._last_loaded = original_loaded
        scheduler_config._last_validation_error = original_error

    print("scheduler config verification ok")


if __name__ == "__main__":
    main()
