import json
from pathlib import Path
from datetime import datetime


STATE_FILE = Path("output/approval_state.json")


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


def save_state(state):
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
        "source": job.get("source"),
        "headline": job.get("headline"),
        "caption": job.get("caption", "General weather update ready for review."),
        "image": job.get("final_output_path"),
        "raw_image": job.get("raw_output_path"),
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


def modify_current_caption(new_caption):
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["caption"] = new_caption
    state["current"]["status"] = "modified"
    state["current"]["modified_at"] = datetime.now().isoformat(timespec="seconds")

    save_state(state)
    return state["current"]


def mark_current_posted(facebook_post_id=None):
    state = load_state()

    if not state.get("current"):
        return None

    state["current"]["status"] = "posted"
    state["current"]["posted_at"] = datetime.now().isoformat(timespec="seconds")
    state["current"]["facebook_post_id"] = facebook_post_id

    state["history"].append(state["current"])
    state["current"] = None

    save_state(state)
    return True