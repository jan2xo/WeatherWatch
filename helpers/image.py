from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


CARD_SIZE = (1080, 1350)

BASE_DIR = Path(__file__).resolve().parent.parent
OVERLAY_PATH = BASE_DIR / "assets" / "overlays" / "NLWW_overlay.png"
FONT_PATH = BASE_DIR / "assets" / "fonts" / "BebasNeue-Regular.otf"
SOURCE_FONT_PATH = BASE_DIR / "assets" / "fonts" / "Arial Narrow.ttf"

CREAM = (245, 239, 217)
HEADLINE_BOX = (70, 24, 1010, 224)
HEADLINE_SPACING = 10


def wrap_text_by_pixels(draw, text, font, max_width):
    words = text.upper().split()
    lines = []
    current = ""

    for word in words:
        test_line = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test_line
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


def fit_font(
    draw,
    text,
    font_path,
    max_width,
    max_height,
    start_size=78,
    min_size=44,
    max_lines=3,
):
    font_size = start_size

    while font_size >= min_size:
        font = ImageFont.truetype(str(font_path), font_size)
        wrapped = wrap_text_by_pixels(draw, text, font, max_width)
        lines = wrapped.splitlines()

        if len(lines) > max_lines:
            font_size -= 2
            continue

        bbox = draw.multiline_textbbox(
            (0, 0),
            wrapped,
            font=font,
            spacing=12,
            align="center",
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if text_width <= max_width and text_height <= max_height:
            return font, wrapped

        font_size -= 2

    font = ImageFont.truetype(str(font_path), min_size)
    return font, wrap_text_by_pixels(draw, text, font, max_width)


def multiline_text_size(draw, text, font, spacing=12):
    bbox = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=spacing,
        align="center",
    )
    return bbox, bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered_multiline_in_box(
    draw,
    text,
    font,
    box,
    fill,
    spacing=12,
):
    bbox, text_width, text_height = multiline_text_size(
        draw,
        text,
        font,
        spacing,
    )
    left, top, right, bottom = box
    x = left + ((right - left) - text_width) / 2 - bbox[0]
    y = top + ((bottom - top) - text_height) / 2 - bbox[1]

    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=fill,
        spacing=spacing,
        align="center",
    )


def draw_right_text(draw, text, y, right_margin=40, fill=CREAM, font=None):
    font = font or ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = CARD_SIZE[0] - right_margin - text_width
    draw.text((x, y), text, font=font, fill=fill)


def compose_weather_card(
    input_path: str,
    output_path: str,
    headline: str,
    source: str = "Map: WINDY",
    overlay_path: str | Path = OVERLAY_PATH,
):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    base = Image.open(input_path).convert("RGBA")
    base = base.resize(CARD_SIZE)

    overlay = Image.open(overlay_path).convert("RGBA")
    overlay = overlay.resize(CARD_SIZE)

    final = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(final)

    headline_font, headline_text = fit_font(
        draw=draw,
        text=headline,
        font_path=FONT_PATH,
        max_width=HEADLINE_BOX[2] - HEADLINE_BOX[0],
        max_height=HEADLINE_BOX[3] - HEADLINE_BOX[1],
        start_size=72,
        min_size=28,
        max_lines=3,
    )

    draw_centered_multiline_in_box(
        draw=draw,
        text=headline_text,
        font=headline_font,
        box=HEADLINE_BOX,
        fill=CREAM,
        spacing=HEADLINE_SPACING,
    )

    source_font = ImageFont.truetype(str(SOURCE_FONT_PATH), 24)
    draw_right_text(
        draw=draw,
        text=source,
        font=source_font,
        y=1288,
        right_margin=40,
        fill=CREAM,
    )

    final.convert("RGB").save(output_path, quality=95)
    return output_path
