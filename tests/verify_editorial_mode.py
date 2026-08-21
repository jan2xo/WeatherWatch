import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.editorial_mode_service import EditorialMode, select_editorial_mode


def verify_templated_always_selectable():
    assert select_editorial_mode("templated", ai_available=False) is EditorialMode.TEMPLATED


def verify_automatic_falls_back_safely():
    assert select_editorial_mode("automatic", ai_available=True) is EditorialMode.AI_ASSISTED
    assert select_editorial_mode("automatic", ai_available=False) is EditorialMode.TEMPLATED


def verify_explicit_ai_failure_is_visible():
    try:
        select_editorial_mode("ai_assisted", ai_available=False)
    except RuntimeError as error:
        assert "TEMPLATED remains available" in str(error)
    else:
        raise AssertionError("Explicit unavailable AI mode must not silently pass")


def verify_invalid_mode_rejected():
    try:
        select_editorial_mode("unknown", ai_available=True)
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown mode must fail")


if __name__ == "__main__":
    verify_templated_always_selectable()
    verify_automatic_falls_back_safely()
    verify_explicit_ai_failure_is_visible()
    verify_invalid_mode_rejected()
    print("editorial mode verification ok")
