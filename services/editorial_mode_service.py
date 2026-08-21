"""Editorial mode selection semantics.

The selector is additive and side-effect free. It does not change the current
Telegram/dashboard control plane; future integration can call it from those
surfaces without making AI a prerequisite.
"""

from enum import Enum


class EditorialMode(str, Enum):
    TEMPLATED = "templated"
    AI_ASSISTED = "ai_assisted"
    AUTOMATIC = "automatic"


def select_editorial_mode(
    requested: EditorialMode | str,
    *,
    ai_available: bool,
) -> EditorialMode:
    try:
        mode = EditorialMode(requested)
    except ValueError as error:
        raise ValueError(f"Unsupported editorial mode: {requested!r}") from error

    if mode is EditorialMode.AUTOMATIC:
        return (
            EditorialMode.AI_ASSISTED
            if ai_available
            else EditorialMode.TEMPLATED
        )

    if mode is EditorialMode.AI_ASSISTED and not ai_available:
        raise RuntimeError(
            "AI ASSISTED unavailable/degraded; TEMPLATED remains available."
        )

    return mode
