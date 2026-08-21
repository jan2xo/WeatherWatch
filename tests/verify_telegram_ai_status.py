import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.telegram_listener import format_ai_fallback_level


def main():
    assert format_ai_fallback_level(0) == "0"
    assert format_ai_fallback_level(None) == "N/A"
    assert format_ai_fallback_level(2) == "2"
    print("telegram AI status fallback formatting verification ok")


if __name__ == "__main__":
    main()
