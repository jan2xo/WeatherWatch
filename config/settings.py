import os

from dotenv import load_dotenv


load_dotenv()


REQUIRED_RUNTIME_ENV = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "FACEBOOK_PAGE_ID",
]


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise ValueError(f"Missing {name} in .env")

    return value


def get_optional_env(name: str) -> str:
    return os.getenv(name, "")


def parse_env_id_list(name: str, required: bool = False) -> set[int]:
    raw = os.getenv(name, "")

    if required and not raw.strip():
        raise ValueError(f"Missing {name} in .env")

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
            "Missing required environment variables in .env: "
            + ", ".join(missing)
        )

    parse_env_id_list("TELEGRAM_ALLOWED_CHAT_IDS", required=True)
    parse_env_id_list("TELEGRAM_ALLOWED_USER_IDS")
