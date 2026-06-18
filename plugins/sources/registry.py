from plugins.sources.panahon import PROVIDER as PANAHON
from plugins.sources.windy import PROVIDER as WINDY
from plugins.sources.meteoblue import PROVIDER as METEOBLUE

PROVIDERS = [
    PANAHON,
    WINDY,
    METEOBLUE,
]


def get_providers():
    return PROVIDERS