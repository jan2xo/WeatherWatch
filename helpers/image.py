from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


def compose_weather_card(
    input_path: str,
    output_path: str,
    title: str = "WEATHERWATCH",
    subtitle: str = "NORTH LUZON UPDATE",
    source: str = "Source: Panahon.gov.ph",
):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(input_path).convert("RGB")
    img = img.resize((1080, 1350))

    draw = ImageDraw.Draw(img)

    # top dark overlay
    draw.rectangle((0, 0, 1080, 160), fill=(0, 0, 0))

    # bottom dark overlay
    draw.rectangle((0, 1230, 1080, 1350), fill=(0, 0, 0))

    # texts
    draw.text((40, 35), title, fill="white")
    draw.text((40, 85), subtitle, fill="white")

    timestamp = datetime.now().strftime("%B %d, %Y • %I:%M %p")
    draw.text((40, 1250), timestamp, fill="white")
    draw.text((40, 1290), source, fill="white")

    img.save(output_path)
    return output_path