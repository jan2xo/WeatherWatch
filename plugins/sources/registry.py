import random

from plugins.sources.panahon import PROVIDER as PANAHON
from plugins.sources.windy import PROVIDER as WINDY
from plugins.sources.meteoblue import PROVIDER as METEOBLUE


PROVIDERS = [
    WINDY,
]


def get_providers():
    providers = PROVIDERS.copy()
    random.shuffle(providers)
    return providers