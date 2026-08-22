import os
import re
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()


REQUIRED_RUNTIME_ENV = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "FACEBOOK_PAGE_ID",
]

ENVIRONMENT_CONTRACT = {
    "TELEGRAM_BOT_TOKEN": ("required_to_start", "secret"),
    "TELEGRAM_CHAT_ID": ("required_to_start", "non_secret"),
    "TELEGRAM_ALLOWED_CHAT_IDS": ("required_to_start", "non_secret"),
    "TELEGRAM_ALLOWED_USER_IDS": ("optional", "non_secret"),
    "FACEBOOK_PAGE_ID": ("required_to_start", "non_secret"),
    "FACEBOOK_PAGE_ACCESS_TOKEN": ("feature_facebook_publish", "secret"),
    "FACEBOOK_GRAPH_API_VERSION": ("feature_facebook", "non_secret"),
    "FACEBOOK_APP_ID": ("feature_facebook_reconnect", "non_secret"),
    "FACEBOOK_APP_SECRET": ("feature_facebook_reconnect", "secret"),
    "FACEBOOK_REDIRECT_URI": ("feature_facebook_reconnect", "non_secret"),
    "ADMIN_DASHBOARD_ENABLED": ("optional", "non_secret"),
    "ADMIN_DASHBOARD_HOST": ("optional", "non_secret"),
    "ADMIN_DASHBOARD_PORT": ("optional", "non_secret"),
    "ADMIN_DASHBOARD_SECRET": ("required_for_public_dashboard", "secret"),
    "PORT": ("managed_runtime", "non_secret"),
    "WEATHERWATCH_RUNTIME_ROOT": ("managed_runtime_durability", "non_secret"),
    "WEATHERWATCH_STATE_BACKEND": ("optional", "non_secret"),
    "WEATHERWATCH_REDIS_URL": ("feature_redis_state", "secret"),
    "WEATHERWATCH_EDITORIAL_MODE": ("optional", "non_secret"),
    "WEATHERWATCH_AI_OPENROUTER_ENABLED": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_OPENROUTER_MODEL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_OPENROUTER_TIMEOUT_SECONDS": ("feature_ai", "non_secret"),
    "OPENROUTER_API_KEY": ("feature_ai", "secret"),
    "OPENROUTER_BASE_URL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_2_ENABLED": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_2_MODEL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_2_TIMEOUT_SECONDS": ("feature_ai", "non_secret"),
    "AI_PROVIDER_2_API_KEY": ("feature_ai", "secret"),
    "AI_PROVIDER_2_BASE_URL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_3_ENABLED": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_3_MODEL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_PROVIDER_3_TIMEOUT_SECONDS": ("feature_ai", "non_secret"),
    "AI_PROVIDER_3_API_KEY": ("feature_ai", "secret"),
    "AI_PROVIDER_3_BASE_URL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_OPENAI_ENABLED": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_OPENAI_MODEL": ("feature_ai", "non_secret"),
    "WEATHERWATCH_AI_OPENAI_TIMEOUT_SECONDS": ("feature_ai", "non_secret"),
    "OPENAI_API_KEY": ("feature_ai", "secret"),
    "OPENAI_BASE_URL": ("feature_ai", "non_secret"),
}


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise ValueError(f"Missing {name} in the runtime environment")

    return value


def get_optional_env(name: str) -> str:
    return os.getenv(name, "")


def parse_env_id_list(name: str, required: bool = False) -> set[int]:
    raw = os.getenv(name, "")

    if required and not raw.strip():
        raise ValueError(f"Missing {name} in the runtime environment")

    ids = set()

    for item in raw.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            ids.add(int(item))
        except ValueError as error:
            raise ValueError(f"{name} must contain comma-separated numeric IDs") from error

    if required and not ids:
        raise ValueError(f"{name} must contain at least one numeric ID")

    return ids


def validate_runtime_config():
    missing = [
        name
        for name in REQUIRED_RUNTIME_ENV
        if not os.getenv(name)
    ]

    if missing:
        raise ValueError(
            "Missing required runtime environment variables: "
            + ", ".join(missing)
        )

    allowed_chat_ids = parse_env_id_list("TELEGRAM_ALLOWED_CHAT_IDS", required=True)
    parse_env_id_list("TELEGRAM_ALLOWED_USER_IDS")

    try:
        outbound_chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    except ValueError as error:
        raise ValueError("TELEGRAM_CHAT_ID must be a numeric ID") from error
    if outbound_chat_id not in allowed_chat_ids:
        raise ValueError("TELEGRAM_CHAT_ID must be listed in TELEGRAM_ALLOWED_CHAT_IDS")

    for name in ("PORT", "ADMIN_DASHBOARD_PORT"):
        value = os.getenv(name)
        if not value:
            continue
        try:
            port = int(value)
        except ValueError as error:
            raise ValueError(f"{name} must be a numeric port") from error
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535")

    dashboard_enabled = os.getenv("ADMIN_DASHBOARD_ENABLED", "true").strip().lower()
    dashboard_is_enabled = dashboard_enabled in {"1", "true", "yes", "on"}
    if os.getenv("PORT") and not dashboard_is_enabled:
        raise ValueError("ADMIN_DASHBOARD_ENABLED must be true when PORT is configured")
    public_dashboard = bool(os.getenv("PORT")) or os.getenv(
        "ADMIN_DASHBOARD_HOST", "127.0.0.1"
    ).strip().lower() not in {"127.0.0.1", "localhost", "::1"}
    if dashboard_is_enabled and public_dashboard:
        if not os.getenv("ADMIN_DASHBOARD_SECRET"):
            raise ValueError("ADMIN_DASHBOARD_SECRET is required for a public dashboard")

    backend = os.getenv("WEATHERWATCH_STATE_BACKEND", "filesystem").strip().lower()
    if backend not in {"filesystem", "redis"}:
        raise ValueError("WEATHERWATCH_STATE_BACKEND must be filesystem or redis")
    if backend == "redis" and not os.getenv("WEATHERWATCH_REDIS_URL"):
        raise ValueError("WEATHERWATCH_REDIS_URL is required for the redis state backend")

    from config.runtime_paths import get_runtime_root

    get_runtime_root()

    reconnect_values = {
        name: bool(os.getenv(name))
        for name in ("FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET", "FACEBOOK_REDIRECT_URI")
    }
    if any(reconnect_values.values()) and not all(reconnect_values.values()):
        raise ValueError(
            "FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, and FACEBOOK_REDIRECT_URI "
            "must be configured together"
        )
    if reconnect_values["FACEBOOK_REDIRECT_URI"]:
        redirect = urlparse(os.environ["FACEBOOK_REDIRECT_URI"])
        if (
            redirect.scheme not in {"http", "https"}
            or not redirect.netloc
            or redirect.username is not None
            or redirect.password is not None
            or redirect.path != "/admin/fb/callback"
            or redirect.params
            or redirect.query
            or redirect.fragment
        ):
            raise ValueError(
                "FACEBOOK_REDIRECT_URI must be an absolute HTTP(S) URL ending "
                "at /admin/fb/callback without credentials, query, or fragment"
            )

    editorial_mode = os.getenv("WEATHERWATCH_EDITORIAL_MODE", "templated").strip()
    if editorial_mode not in {"templated", "ai_assisted", "automatic"}:
        raise ValueError("WEATHERWATCH_EDITORIAL_MODE is unsupported")

    graph_version = os.getenv("FACEBOOK_GRAPH_API_VERSION", "v26.0").strip()
    if not re.fullmatch(r"v[1-9][0-9]*\.0", graph_version):
        raise ValueError("FACEBOOK_GRAPH_API_VERSION must look like v26.0")


def get_environment_contract_status(environ=None):
    """Return secret-free configuration presence and feature readiness."""

    environment = os.environ if environ is None else environ
    required_missing = [name for name in REQUIRED_RUNTIME_ENV if not environment.get(name)]
    reconnect_names = (
        "FACEBOOK_APP_ID",
        "FACEBOOK_APP_SECRET",
        "FACEBOOK_REDIRECT_URI",
    )
    backend = environment.get("WEATHERWATCH_STATE_BACKEND", "filesystem").strip().lower()
    return {
        "required_configuration": (
            "ready" if not required_missing else "unavailable"
        ),
        "required_missing": required_missing,
        "telegram": {
            "configured": all(environment.get(name) for name in REQUIRED_RUNTIME_ENV[:3]),
            "authorization_configured": bool(
                environment.get("TELEGRAM_ALLOWED_CHAT_IDS")
            ),
        },
        "facebook": {
            "page_configured": bool(environment.get("FACEBOOK_PAGE_ID")),
            "publish_token_env_configured": bool(
                environment.get("FACEBOOK_PAGE_ACCESS_TOKEN")
            ),
            "reconnect_configured": all(environment.get(name) for name in reconnect_names),
        },
        "state": {
            "backend": backend,
            "redis_url_configured": bool(environment.get("WEATHERWATCH_REDIS_URL")),
            "runtime_root_configured": bool(
                environment.get("WEATHERWATCH_RUNTIME_ROOT")
            ),
        },
        "dashboard": {
            "enabled": environment.get("ADMIN_DASHBOARD_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            "secret_configured": bool(environment.get("ADMIN_DASHBOARD_SECRET")),
            "managed_port_configured": bool(environment.get("PORT")),
        },
    }
