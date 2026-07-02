import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.telegram_listener import parse_modify_text


def main():
    plural = parse_modify_text(
        "/modify\n"
        "HEADLINES:\n"
        "TROPICAL DEPRESSION\n"
        "#HenryPH\n"
        "PATULOY NA BINABANTAYAN\n\n"
        "CAPTIONS:\n"
        "🌀 TROPICAL DEPRESSION #HenryPH PATULOY NA BINABANTAYAN!\n\n"
        "UPDATE:\n"
        "Test caption."
    )
    assert plural["headline"] == (
        "TROPICAL DEPRESSION\n"
        "#HenryPH\n"
        "PATULOY NA BINABANTAYAN"
    )
    assert plural["caption"] == (
        "🌀 TROPICAL DEPRESSION #HenryPH PATULOY NA BINABANTAYAN!\n\n"
        "UPDATE:\n"
        "Test caption."
    )

    singular = parse_modify_text(
        "/modify\n"
        "HEADLINE : Custom graphic headline\n"
        "CAPTION : Exact Facebook caption."
    )
    assert singular == {
        "headline": "CUSTOM GRAPHIC HEADLINE",
        "caption": "Exact Facebook caption.",
    }

    clean_caption = parse_modify_text(
        "/modify\n🌀 TROPICAL STORM #GardoPH PATULOY NA BINABANTAYAN!"
    )
    assert clean_caption == {
        "caption": "🌀 TROPICAL STORM #GardoPH PATULOY NA BINABANTAYAN!"
    }

    print("Modify parser verification ok")


if __name__ == "__main__":
    main()
