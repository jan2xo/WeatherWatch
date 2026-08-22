import threading
import os  # compatibility surface used by existing atomic-write safety tests
from datetime import datetime, timedelta

from config.runtime_paths import runtime_path
from services.post_type_config_service import get_job_post_type_defaults
from storage.state_repository import get_state_repository


STATE_FILE = runtime_path("state/approval_state.json")
HISTORY_RETENTION_DAYS = 7
HISTORY_DATE_FIELDS = [
    "posted_at",
    "rejected_at",
    "publish_failed_at",
    "approved_at",
    "modified_at",
    "created_at",
]
_STATE_LOCK = threading.RLock()


def default_state():
    return {
        "current": None,
        "history": []
    }


def load_state():
    with _STATE_LOCK:
        return get_state_repository(STATE_FILE, state_key="approval_state").load(
            default_state
        )


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
        get_state_repository(STATE_FILE, state_key="approval_state").save(state)


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
            "requested_editorial_mode": job.get(
                "requested_editorial_mode", "templated"
            ),
            "editorial_mode": job.get("editorial_mode", "templated"),
            "ai_status": job.get("ai_status", "not_requested"),
            "ai_provider": job.get("ai_provider"),
            "ai_model": job.get("ai_model"),
            "ai_fallback_level": job.get("ai_fallback_level"),
            "ai_validation_state": job.get("ai_validation_state", "not_run"),
            "editorial_provenance": job.get("editorial_provenance"),
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
