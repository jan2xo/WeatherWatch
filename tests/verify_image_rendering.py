import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.image_rendering_service import (
    TARGET_SIZE,
    apply_image_fit,
    crop,
    load_config,
    save_config,
)


SOURCE_SIZES = {
    "portrait mobile screenshot": (1170, 2532),
    "tall mobile screenshot": (1080, 2400),
    "landscape screenshot": (2532, 1170),
    "square image": (1600, 1600),
    "wide image": (3000, 1000),
    "very tall image": (1000, 3000),
}


def make_quadrant_image(size):
    width, height = size
    image = Image.new("RGB", size, (0, 0, 64))
    draw = ImageDraw.Draw(image)
    draw.rectangle((width // 2, 0, width, height // 2), fill=(255, 0, 64))
    draw.rectangle((0, height // 2, width // 2, height), fill=(0, 255, 64))
    draw.rectangle(
        (width // 2, height // 2, width, height),
        fill=(255, 255, 64),
    )
    marker_half_size = max(20, min(width, height) // 20)
    draw.rectangle(
        (
            width // 2 - marker_half_size,
            height // 2 - marker_half_size,
            width // 2 + marker_half_size,
            height // 2 + marker_half_size,
        ),
        fill=(17, 33, 201),
    )

    return image


def assert_center_preserved(source, rendered):
    source_center = source.getpixel((source.width // 2, source.height // 2))
    rendered_center = rendered.getpixel(
        (rendered.width // 2, rendered.height // 2)
    )
    assert source_center == rendered_center


def run():
    with tempfile.TemporaryDirectory() as temporary_directory:
        config_path = Path(temporary_directory) / "image_rendering.json"

        for mode in ("stretch", "smartfit", "crop"):
            save_config(
                {
                    "fit_mode": mode,
                    "target_width": 1080,
                    "target_height": 1350,
                },
                config_path=config_path,
            )

            for label, size in SOURCE_SIZES.items():
                source = make_quadrant_image(size)
                rendered = apply_image_fit(source, config_path=config_path)
                assert rendered.size == TARGET_SIZE, (mode, label, rendered.size)

                if mode in ("smartfit", "crop"):
                    assert_center_preserved(source, rendered)

        large_source = make_quadrant_image((1800, 2000))
        cropped = crop(large_source)
        expected_left = (large_source.width - TARGET_SIZE[0]) // 2
        expected_top = (large_source.height - TARGET_SIZE[1]) // 2
        assert cropped.getpixel((0, 0)) == large_source.getpixel(
            (expected_left, expected_top)
        )

        small_source = make_quadrant_image((400, 500))
        assert crop(small_source).size == TARGET_SIZE

        config_path.write_text(
            json.dumps({
                "fit_mode": "unsupported",
                "target_width": 999,
                "target_height": 999,
            }),
            encoding="utf-8",
        )
        fallback = load_config(config_path=config_path)
        assert fallback["fit_mode"] == "smartfit"
        assert apply_image_fit(
            make_quadrant_image((1200, 800)),
            config_path=config_path,
        ).size == TARGET_SIZE

    print("Image rendering verification passed.")


if __name__ == "__main__":
    run()
