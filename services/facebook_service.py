from pathlib import Path
from urllib.parse import urlencode

import requests

from config.settings import get_optional_env, get_required_env
from storage.facebook_token_store import (
    load_facebook_token_state,
    public_token_state,
    save_page_token,
    update_token_health,
    utc_now,
)
from storage.approval_store import (
    get_current_job,
    mark_current_posted,
    mark_current_publish_failed,
    mark_current_publishing,
)


GRAPH_API_VERSION = "v20.0"
GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_LOGIN_URL = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"
FACEBOOK_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
]


def safe_graph_error(response):
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"

    error = data.get("error", {})
    message = error.get("message") or response.reason or "Facebook request failed"
    code = error.get("code")

    if code:
        return f"{message} (code {code})"

    return message


def get_facebook_config():
    page_id = get_required_env("FACEBOOK_PAGE_ID")
    token_state = load_facebook_token_state()

    if (
        token_state.get("access_token")
        and str(token_state.get("page_id")) == str(page_id)
        and token_state.get("status") == "active"
    ):
        try:
            page_data = validate_page_token(page_id, token_state["access_token"])
            update_token_health("active", page_name=page_data.get("name"))
            return page_id, token_state["access_token"]
        except Exception as error:
            update_token_health("invalid", last_error=str(error))

    fallback = get_optional_env("FACEBOOK_PAGE_ACCESS_TOKEN")

    if fallback:
        return page_id, fallback

    raise ValueError(
        "No active Facebook Page token found. Reconnect Facebook or set FACEBOOK_PAGE_ACCESS_TOKEN."
    )


def get_facebook_oauth_config():
    return {
        "app_id": get_required_env("FACEBOOK_APP_ID"),
        "app_secret": get_required_env("FACEBOOK_APP_SECRET"),
        "redirect_uri": get_required_env("FACEBOOK_REDIRECT_URI"),
        "page_id": get_required_env("FACEBOOK_PAGE_ID"),
    }


def get_facebook_caption(job):
    return job.get("captions", {}).get("facebook") or job.get("caption", "")


def get_app_access_token():
    config = get_facebook_oauth_config()
    return f"{config['app_id']}|{config['app_secret']}"


def build_facebook_login_url(state="weatherwatch"):
    config = get_facebook_oauth_config()
    query = urlencode({
        "client_id": config["app_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": ",".join(FACEBOOK_SCOPES),
        "response_type": "code",
        "state": state,
    })

    return f"{FACEBOOK_LOGIN_URL}?{query}"


def exchange_code_for_short_lived_user_token(code):
    config = get_facebook_oauth_config()
    response = requests.get(
        f"{GRAPH_API_BASE_URL}/oauth/access_token",
        params={
            "client_id": config["app_id"],
            "client_secret": config["app_secret"],
            "redirect_uri": config["redirect_uri"],
            "code": code,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"Facebook OAuth failed: {safe_graph_error(response)}")

    return response.json()["access_token"]


def exchange_for_long_lived_user_token(short_lived_token):
    config = get_facebook_oauth_config()
    response = requests.get(
        f"{GRAPH_API_BASE_URL}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": config["app_id"],
            "client_secret": config["app_secret"],
            "fb_exchange_token": short_lived_token,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"Facebook token exchange failed: {safe_graph_error(response)}")

    return response.json()["access_token"]


def fetch_facebook_pages(user_access_token):
    response = requests.get(
        f"{GRAPH_API_BASE_URL}/me/accounts",
        params={
            "fields": "id,name,access_token",
            "access_token": user_access_token,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"Facebook Pages fetch failed: {safe_graph_error(response)}")

    return response.json().get("data", [])


def select_configured_page(pages):
    page_id = get_required_env("FACEBOOK_PAGE_ID")

    for page in pages:
        if str(page.get("id")) == str(page_id):
            return page

    raise RuntimeError("Configured Facebook Page ID was not found for this Facebook account.")


def validate_page_token(page_id, access_token):
    response = requests.get(
        f"{GRAPH_API_BASE_URL}/{page_id}",
        params={
            "fields": "id,name",
            "access_token": access_token,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"Facebook token validation failed: {safe_graph_error(response)}")

    data = response.json()

    if str(data.get("id")) != str(page_id):
        raise RuntimeError("Facebook token validation returned the wrong Page ID.")

    return data


def reconnect_facebook_with_code(code):
    short_lived_token = exchange_code_for_short_lived_user_token(code)
    long_lived_token = exchange_for_long_lived_user_token(short_lived_token)
    pages = fetch_facebook_pages(long_lived_token)
    page = select_configured_page(pages)
    page_access_token = page.get("access_token")

    if not page_access_token:
        raise RuntimeError("Facebook did not return a Page access token for the configured Page.")

    page_data = validate_page_token(page["id"], page_access_token)
    page_summary = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "configured": str(item.get("id")) == str(page["id"]),
        }
        for item in pages
    ]

    save_page_token(
        page_id=page["id"],
        page_name=page_data.get("name") or page.get("name"),
        access_token=page_access_token,
        token_type="page",
        source="oauth",
        pages=page_summary,
    )
    state = update_token_health("active", page_name=page_data.get("name") or page.get("name"))

    return public_token_state(state)


def get_facebook_access_token():
    page_id = get_required_env("FACEBOOK_PAGE_ID")
    token_state = load_facebook_token_state()

    if (
        token_state.get("access_token")
        and str(token_state.get("page_id")) == str(page_id)
        and token_state.get("status") == "active"
    ):
        return token_state["access_token"]

    fallback = get_optional_env("FACEBOOK_PAGE_ACCESS_TOKEN")

    if fallback:
        return fallback

    raise ValueError(
        "No active Facebook Page token found. Reconnect Facebook or set FACEBOOK_PAGE_ACCESS_TOKEN."
    )


def get_facebook_token_source():
    page_id = get_required_env("FACEBOOK_PAGE_ID")
    token_state = load_facebook_token_state()

    if (
        token_state.get("access_token")
        and str(token_state.get("page_id")) == str(page_id)
        and token_state.get("status") == "active"
    ):
        return "token_store"

    if get_optional_env("FACEBOOK_PAGE_ACCESS_TOKEN"):
        return "env_fallback"

    return "missing"


def check_facebook_token_health():
    page_id = get_required_env("FACEBOOK_PAGE_ID")
    source = get_facebook_token_source()

    if source == "missing":
        state = load_facebook_token_state()
        return {
            **public_token_state(state),
            "configured_page_id": page_id,
            "source": "missing",
            "status": "missing",
            "last_checked": utc_now(),
            "last_error": "No Facebook Page token is configured.",
        }

    try:
        access_token = get_facebook_access_token()
        page_data = validate_page_token(page_id, access_token)

        if source == "token_store":
            state = update_token_health("active", page_name=page_data.get("name"))
            return {
                **public_token_state(state),
                "configured_page_id": page_id,
                "source": source,
            }

        return {
            "configured_page_id": page_id,
            "page_id": page_data.get("id"),
            "page_name": page_data.get("name"),
            "token_type": "page",
            "last_updated": None,
            "source": source,
            "status": "active",
            "last_checked": utc_now(),
            "last_error": None,
        }

    except Exception as error:
        if source == "token_store":
            state = update_token_health("invalid", last_error=str(error))
            return {
                **public_token_state(state),
                "configured_page_id": page_id,
                "source": source,
            }

        return {
            "configured_page_id": page_id,
            "page_id": page_id,
            "page_name": None,
            "token_type": "page",
            "last_updated": None,
            "source": source,
            "status": "invalid",
            "last_checked": utc_now(),
            "last_error": str(error),
        }


def get_facebook_status():
    page_id = get_required_env("FACEBOOK_PAGE_ID")
    state = load_facebook_token_state()
    source = get_facebook_token_source()

    if source == "token_store":
        return {
            **public_token_state(state),
            "configured_page_id": page_id,
            "source": source,
        }

    return {
        "configured_page_id": page_id,
        "page_id": state.get("page_id"),
        "page_name": state.get("page_name"),
        "token_type": state.get("token_type"),
        "last_updated": state.get("last_updated"),
        "source": source,
        "status": "available" if source == "env_fallback" else "missing",
        "last_checked": state.get("last_checked"),
        "last_error": state.get("last_error"),
    }


def publish_photo_post(image_path: str, caption: str):
    page_id, page_access_token = get_facebook_config()

    image_file = Path(image_path)

    if not image_file.exists():
        raise FileNotFoundError(f"Facebook image not found: {image_file}")

    url = f"https://graph.facebook.com/v20.0/{page_id}/photos"

    with image_file.open("rb") as photo:
        response = requests.post(
            url,
            data={
                "caption": caption,
                "access_token": page_access_token,
                "published": "true",
            },
            files={
                "source": photo,
            },
            timeout=60,
        )

    if not response.ok:
        raise RuntimeError(f"Facebook publish failed: {safe_graph_error(response)}")

    return response.json()


def publish_current_job():
    job = get_current_job()

    if not job:
        raise ValueError("No current job to publish.")

    if job.get("status") not in {"approved", "publish_failed"}:
        raise ValueError(f"Current job is not approved. Status: {job.get('status')}")

    mark_current_publishing()

    try:
        result = publish_photo_post(
            image_path=job["image"],
            caption=get_facebook_caption(job),
        )
    except Exception as error:
        mark_current_publish_failed(error)
        raise

    facebook_post_id = result.get("post_id") or result.get("id")
    mark_current_posted(facebook_post_id=facebook_post_id)

    return {
        "success": True,
        "facebook_result": result,
        "facebook_post_id": facebook_post_id,
    }
