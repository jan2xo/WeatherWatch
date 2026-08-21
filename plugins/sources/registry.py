import random

from plugins.sources.panahon import PROVIDER as PANAHON
from plugins.sources.windy import PROVIDER as WINDY
from plugins.sources.meteoblue import PROVIDER as METEOBLUE


PROVIDERS = [
    WINDY,
]

KNOWN_PROVIDERS = {
    provider["name"]: provider
    for provider in (WINDY, PANAHON, METEOBLUE)
}


def get_providers():
    providers = PROVIDERS.copy()
    random.shuffle(providers)
    return providers


def resolve_providers(requested_provider=None):
    """Resolve normal or explicit provider selection from the active registry."""
    requested = (requested_provider or "default").strip().lower()
    if requested == "default":
        return get_providers()

    if requested not in KNOWN_PROVIDERS:
        raise ValueError(f"Unknown weather provider: {requested}")

    selected = [provider for provider in PROVIDERS if provider["name"] == requested]
    if not selected:
        raise ValueError(f"Weather provider is disabled or unavailable: {requested}")
    return selected
