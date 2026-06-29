import json
import os
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

from services.post_type_config_service import get_job_post_type_defaults


STATE_FILE = Path("state/approval_state.json")
HISTORY_RETENTION_DAYS = 7
HISTORY_DATE_FIELDS = [
    "posted_at",
    "rejected_at",
    "publish_failed_at",
    "approved_at",
    "modified_at",
    "created_at",
]
STATE_READ_ATTEMPTS = 3
STATE_READ_RETRY_SECONDS = 0.02
_STATE_LOCK = threading.RLock()


def default_state():
    return {
        "current": None,
        "history": []
    }


def load_state():
    with _STATE_LOCK:
        if not STATE_FILE.exists():
            return default_state()

        last_error = None
        for attempt in range(STATE_READ_ATTEMPTS):
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except FileNotFoundError:
                if not STATE_FILE.exists():
                    return default_state()
                last_error = FileNotFoundError(
                    "Approval state temporarily unavailable."
                )
            except json.JSONDecodeError as error:
                last_error = error

            if attempt < STATE_READ_ATTEMPTS - 1:
                time.sleep(STATE_READ_RETRY_SECONDS)

        raise RuntimeError(
            "Approval state could not be read safely. "
            "The existing state file was not replaced."
        ) from last_error


def parse_timestamp(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def history_timestamp(job):
    for field in HISTORY_DATE_FIELDS:
        timestamp = parse_timestamp(job.get(field))

        if timestamp:
            return timestamp

    return None


def prune_history(state):
    cutoff = datetime.now() - timedelta(days=HISTORY_RETENTION_DAYS)
    history = []

    for job in state.get("history", []):
        timestamp = history_timestamp(job)

        if not timestamp or timestamp >= cutoff:
            history.append(job)

    state["history"] = history
    return state


def save_state(state):
    with _STATE_LOCK:
        state = prune_history(state)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=STATE_FILE.parent,
                prefix=f".{STATE_FILE.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(state, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())

            os.replace(temporary_path, STATE_FILE)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()


def create_current_job(job):
    with _STATE_LOCK:
        state = load_state()
        post_type_defaults = get_job_post_type_defaults()

        job_id = (
            job.get("job_id")
            or datetime.now().strftime("%y%m%d-%H%M%S")
        )

        current = {
            "job_id": job_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "page": job.get("page", "north_luzon_weather_watch"),
            "provider": job.get("provider"),
            "provider_display": job.get("provider_display"),
            "provider_url": job.get("provider_url"),
            "source": job.get("source"),
            "headline": job.get("headline"),
            "captions": job.get("captions", {}),
            "caption": job.get("captions", {}).get(
                "facebook",
                job.get("caption", "")
            ),
            "image": job.get("final_output_path"),
            "raw_image": job.get("raw_output_path"),
            "framing_decision": job.get("framing_decision"),
            "post_type": job.get(
                "post_type",
                post_type_defaults["post_type"],
            ),
            "available_post_types": job.get(
                "available_post_types",
                post_type_defaults["available_post_types"],
            ),
            "suggested_post_type": job.get(
                "suggested_post_type",
                post_type_defaults["suggested_post_type"],
            ),
            "post_type_reason": job.get(
                "post_type_reason",
                post_type_defaults["post_type_reason"],
            ),
            "windy_layer": job.get("windy_layer"),
            "windy_layer_label": job.get("windy_layer_label"),
            "suggested_windy_layer": job.get("suggested_windy_layer"),
            "windy_url": job.get("windy_url"),
        }

        state["current"] = current
        save_state(state)

        return current


def get_current_job():
    return load_state().get("current")


def approve_current_job():
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        state["current"]["status"] = "approved"
        state["current"]["approved_at"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)

        return state["current"]


def reject_current_job():
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        state["current"]["status"] = "rejected"
        state["current"]["rejected_at"] = datetime.now().isoformat(timespec="seconds")

        state["history"].append(state["current"])
        state["current"] = None

        save_state(state)
        return True


def update_current_job(fields, preserve_status=False):
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        for key, value in fields.items():
            state["current"][key] = value

        if not preserve_status:
            state["current"]["status"] = "modified"
            state["current"]["modified_at"] = datetime.now().isoformat(
                timespec="seconds"
            )

        save_state(state)
        return state["current"]


def mark_current_publishing():
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        state["current"]["status"] = "publishing"
        state["current"]["publishing_at"] = datetime.now().isoformat(timespec="seconds")
        state["current"].pop("last_error", None)

        save_state(state)
        return state["current"]


def mark_current_publish_failed(error):
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        state["current"]["status"] = "publish_failed"
        state["current"]["publish_failed_at"] = datetime.now().isoformat(timespec="seconds")
        state["current"]["last_error"] = str(error)

        save_state(state)
        return state["current"]


def mark_current_posted(facebook_post_id=None):
    with _STATE_LOCK:
        state = load_state()

        if not state.get("current"):
            return None

        state["current"]["status"] = "posted"
        state["current"]["posted_at"] = datetime.now().isoformat(timespec="seconds")
        state["current"]["facebook_post_id"] = facebook_post_id
        state["current"].pop("last_error", None)

        state["history"].append(state["current"])
        state["current"] = None

        save_state(state)
        return True
