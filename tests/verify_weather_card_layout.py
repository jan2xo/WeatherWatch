import sys
from pathlib import Path

from PIL import Image, ImageDraw


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.image import (
    FONT_PATH,
    HEADLINE_BOX,
    HEADLINE_SPACING,
    fit_font,
    multiline_text_size,
)


def main():
    image = Image.new("RGB", (1080, 1350))
    draw = ImageDraw.Draw(image)
    headline = (
        "BAGYONG TATAWAGING INDAY, LALO PANG LUMALAKAS "
        "HABANG PAPALAPIT NG PAR"
    )
    max_width = HEADLINE_BOX[2] - HEADLINE_BOX[0]
    max_height = HEADLINE_BOX[3] - HEADLINE_BOX[1]

    font, wrapped = fit_font(
        draw=draw,
        text=headline,
        font_path=FONT_PATH,
        max_width=max_width,
        max_height=max_height,
        start_size=72,
        min_size=28,
        max_lines=3,
    )
    _, text_width, text_height = multiline_text_size(
        draw,
        wrapped,
        font,
        HEADLINE_SPACING,
    )

    assert text_width <= max_width
    assert text_height <= max_height
    assert len(wrapped.splitlines()) <= 3
    assert "TATAWAGING INDAY" in wrapped
    assert "PAPALAPIT" in wrapped

    print("Weather card headline layout verification ok")


if __name__ == "__main__":
    main()
