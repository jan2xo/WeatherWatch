import copy
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.runtime_paths import runtime_config_path, runtime_path


CONFIG_PATH = runtime_config_path("config/scheduler.json")
BACKUP_DIR = runtime_path("data/scheduler_backups")
UPLOAD_DIR = runtime_path("data/scheduler_uploads")
MAX_SCHEDULER_UPLOAD_BYTES = 100 * 1024
MAX_SCHEDULER_BACKUPS = 10
SUPPORTED_ACTIONS = {"weather_update"}
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

DEFAULT_CONFIG = {
    "version": "1.0",
    "enabled": True,
    "timezone": "Asia/Manila",
    "pending_job_policy": {
        "auto_reject_before_next_run": True,
        "reject_statuses": ["pending", "modified"],
    },
    "jobs": [
        {
            "id": "morning_update",
            "enabled": True,
            "time": "05:00",
            "action": "weather_update",
            "provider": "default",
            "skip_if_pending_job_exists": True,
        },
        {
            "id": "midday_update",
            "enabled": True,
            "time": "11:00",
            "action": "weather_update",
            "provider": "default",
            "skip_if_pending_job_exists": True,
        },
        {
            "id": "evening_update",
            "enabled": True,
            "time": "17:00",
            "action": "weather_update",
            "provider": "default",
            "skip_if_pending_job_exists": True,
        },
    ],
}

_config_cache = None
_last_loaded = None
_last_validation_error = None


def default_scheduler_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def validate_scheduler_config(config):
    if not isinstance(config, dict):
        raise ValueError("Scheduler configuration must be a JSON object.")

    for key in ("version", "enabled", "timezone", "jobs"):
        if key not in config:
            raise ValueError(f"Missing required scheduler key: {key}")

    if not isinstance(config["version"], str) or not config["version"].strip():
        raise ValueError("version must be a non-empty string.")
    if not isinstance(config["enabled"], bool):
        raise ValueError("enabled must be true or false.")
    if not isinstance(config["timezone"], str) or not config["timezone"].strip():
        raise ValueError("timezone must be a non-empty IANA timezone.")

    try:
        ZoneInfo(config["timezone"])
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"Unknown scheduler timezone: {config['timezone']}"
        ) from error

    jobs = config["jobs"]
    if not isinstance(jobs, list):
        raise ValueError("jobs must be an array.")

    pending_policy = config.get("pending_job_policy", {})
    if not isinstance(pending_policy, dict):
        raise ValueError("pending_job_policy must be an object.")
    auto_reject = pending_policy.get(
        "auto_reject_before_next_run",
        False,
    )
    if not isinstance(auto_reject, bool):
        raise ValueError(
            "pending_job_policy.auto_reject_before_next_run "
            "must be true or false."
        )
    reject_statuses = pending_policy.get(
        "reject_statuses",
        ["pending", "modified"],
    )
    if (
        not isinstance(reject_statuses, list)
        or any(
            status not in {"pending", "modified"}
            for status in reject_statuses
        )
    ):
        raise ValueError(
            "pending_job_policy.reject_statuses may contain only "
            "pending and modified."
        )

    job_ids = set()
    for index, job in enumerate(jobs):
        path = f"jobs[{index}]"
        if not isinstance(job, dict):
            raise ValueError(f"{path} must be an object.")

        for key in ("id", "enabled", "time", "action"):
            if key not in job:
                raise ValueError(f"Missing required key: {path}.{key}")

        job_id = job["id"]
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError(f"{path}.id must be a non-empty string.")
        if job_id in job_ids:
            raise ValueError(f"Duplicate scheduler job ID: {job_id}")
        job_ids.add(job_id)

        if not isinstance(job["enabled"], bool):
            raise ValueError(f"{path}.enabled must be true or false.")
        if not isinstance(job["time"], str) or not TIME_PATTERN.fullmatch(
            job["time"]
        ):
            raise ValueError(f"{path}.time must use HH:MM 24-hour format.")
        if job["action"] not in SUPPORTED_ACTIONS:
            raise ValueError(
                f"{path}.action is unsupported: {job['action']!r}"
            )
        if "provider" in job and job["provider"] != "default":
            raise ValueError(
                f"{path}.provider must be 'default' for WINDY-only operation."
            )
        if (
            "skip_if_pending_job_exists" in job
            and not isinstance(job["skip_if_pending_job_exists"], bool)
        ):
            raise ValueError(
                f"{path}.skip_if_pending_job_exists must be true or false."
            )

    return True


def validate_scheduler_upload_size(path):
    if Path(path).stat().st_size > MAX_SCHEDULER_UPLOAD_BYTES:
        raise ValueError("Scheduler upload rejected: file too large.")


def load_scheduler_config_file(path=CONFIG_PATH):
    config_path = Path(path)
    validate_scheduler_upload_size(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_scheduler_config(config)
    return config


def reload_scheduler_config():
    global _config_cache, _last_loaded, _last_validation_error

    try:
        config = load_scheduler_config_file(CONFIG_PATH)
    except Exception as error:
        _last_validation_error = str(error)
        raise

    _config_cache = config
    _last_loaded = datetime.now().isoformat(timespec="seconds")
    _last_validation_error = None
    return copy.deepcopy(_config_cache)


def get_scheduler_config():
    global _config_cache, _last_loaded, _last_validation_error

    if _config_cache is not None:
        return copy.deepcopy(_config_cache)

    try:
        return reload_scheduler_config()
    except Exception as error:
        _last_validation_error = str(error)
        _config_cache = default_scheduler_config()
        _last_loaded = datetime.now().isoformat(timespec="seconds")
        return copy.deepcopy(_config_cache)


def save_scheduler_config(config, path=CONFIG_PATH):
    validate_scheduler_config(config)
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)
    return copy.deepcopy(config)


def backup_current_scheduler_config():
    if not CONFIG_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    backup_path = BACKUP_DIR / f"scheduler.{timestamp}.json"
    backup_path.write_text(
        CONFIG_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    backups = sorted(
        BACKUP_DIR.glob("scheduler.*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_SCHEDULER_BACKUPS:]:
        old_backup.unlink()
    return backup_path


def replace_scheduler_config_from_file(uploaded_path):
    config = load_scheduler_config_file(uploaded_path)
    backup_current_scheduler_config()
    save_scheduler_config(config, CONFIG_PATH)
    reload_scheduler_config()
    return get_scheduler_status()


def get_scheduler_status():
    try:
        config = load_scheduler_config_file(CONFIG_PATH)
        validation_status = "valid"
        validation_error = None
    except Exception as error:
        config = _config_cache or default_scheduler_config()
        validation_status = "invalid"
        validation_error = str(error)

    enabled_jobs = [
        job for job in config.get("jobs", [])
        if job.get("enabled")
    ]
    return {
        "config_path": str(CONFIG_PATH),
        "version": config.get("version"),
        "enabled": config.get("enabled"),
        "timezone": config.get("timezone"),
        "validation_status": validation_status,
        "last_loaded": _last_loaded,
        "last_validation_error": (
            validation_error or _last_validation_error
        ),
        "enabled_job_count": len(enabled_jobs),
        "auto_reject_before_next_run": (
            config.get("pending_job_policy", {})
            .get("auto_reject_before_next_run", False)
        ),
        "auto_reject_statuses": (
            config.get("pending_job_policy", {})
            .get("reject_statuses", [])
        ),
        "enabled_jobs": [
            {
                "id": job.get("id"),
                "time": job.get("time"),
                "action": job.get("action"),
            }
            for job in enabled_jobs
        ],
    }


def scheduler_json_preview(limit=3500):
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("Scheduler configuration does not exist.")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n\n... shortened preview ..."


def starter_scheduler_json():
    return json.dumps(default_scheduler_config(), indent=2)
