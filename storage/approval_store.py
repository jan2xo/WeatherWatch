import json
from pathlib import Path
from datetime import datetime, timedelta


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


def default_state():
    return {
        "current": None,
        "history": []
    }


def load_state():
    if not STATE_FILE.exists():
        return default_state()

    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return default_state()


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
    state = prune_history(state)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def create_current_job(job):
    state = load_state()

    job_id = job.get("job_id") or datetime.now().strftime("%y%m%d-%H%M%S")

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
    }

    state["current"] = current
    save_state(state)

    return current


def get_current_job():
    return load_state().get("current")


def approve_current_job():
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["status"] = "approved"
    state["current"]["approved_at"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)

    return state["current"]


def reject_current_job():
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["status"] = "rejected"
    state["current"]["rejected_at"] = datetime.now().isoformat(timespec="seconds")

    state["history"].append(state["current"])
    state["current"] = None

    save_state(state)
    return True


def update_current_job(fields):
    state = load_state()

    if not state.get("current"):
        return None

    for key, value in fields.items():
        state["current"][key] = value

    state["current"]["status"] = "modified"
    state["current"]["modified_at"] = datetime.now().isoformat(timespec="seconds")

    save_state(state)
    return state["current"]


def mark_current_publishing():
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["status"] = "publishing"
    state["current"]["publishing_at"] = datetime.now().isoformat(timespec="seconds")
    state["current"].pop("last_error", None)

    save_state(state)
    return state["current"]


def mark_current_publish_failed(error):
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["status"] = "publish_failed"
    state["current"]["publish_failed_at"] = datetime.now().isoformat(timespec="seconds")
    state["current"]["last_error"] = str(error)

    save_state(state)
    return state["current"]


def mark_current_posted(facebook_post_id=None):
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
