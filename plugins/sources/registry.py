from plugins.sources.windy import PROVIDER as WINDY


PROVIDERS = [
    WINDY,
]


def get_providers():
    """Return the sole operational map provider."""
    return PROVIDERS.copy()
