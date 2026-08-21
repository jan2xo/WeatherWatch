from datetime import datetime
from pathlib import Path

from storage.state_repository import get_state_repository


STATE_FILE = Path("state/facebook_token_state.json")


def utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def default_state():
    return {
        "page_id": None,
        "page_name": None,
        "access_token": None,
        "token_type": None,
        "last_updated": None,
        "source": None,
        "status": "missing",
        "last_checked": None,
        "last_error": None,
        "pages": [],
    }


def load_facebook_token_state():
    state = get_state_repository(
        STATE_FILE, state_key="facebook_token_state"
    ).load(default_state)
    return {
        **default_state(),
        **state,
    }


def save_facebook_token_state(state):
    get_state_repository(STATE_FILE, state_key="facebook_token_state").save(state)
    return state


def save_page_token(page_id, page_name, access_token, token_type="page", source="oauth", pages=None):
    state = {
        **load_facebook_token_state(),
        "page_id": page_id,
        "page_name": page_name,
        "access_token": access_token,
        "token_type": token_type,
        "last_updated": utc_now(),
        "source": source,
        "status": "active",
        "last_checked": None,
        "last_error": None,
        "pages": pages or [],
    }

    return save_facebook_token_state(state)


def update_token_health(status, last_error=None, page_name=None):
    state = load_facebook_token_state()
    state["status"] = status
    state["last_checked"] = utc_now()
    state["last_error"] = last_error

    if page_name:
        state["page_name"] = page_name

    return save_facebook_token_state(state)


def public_token_state(state=None):
    state = state or load_facebook_token_state()

    return {
        "page_id": state.get("page_id"),
        "page_name": state.get("page_name"),
        "token_type": state.get("token_type"),
        "last_updated": state.get("last_updated"),
        "source": state.get("source"),
        "status": state.get("status"),
        "last_checked": state.get("last_checked"),
        "last_error": state.get("last_error"),
    }
