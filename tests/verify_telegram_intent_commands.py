import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.telegram_listener as listener


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


async def verify_handlers():
    original_fit = listener.set_fit_mode
    original_windy = listener.control_set_windy_layer
    original_post_type = listener.control_set_post_type
    original_get_job = listener.get_current_job
    calls = []

    try:
        listener.set_fit_mode = lambda mode: calls.append(
            ("image_fit", mode)
        ) or {
            "fit_mode": mode,
            "target_width": 1080,
            "target_height": 1350,
        }
        listener.control_set_windy_layer = lambda layer_id: calls.append(
            ("windy_layer", layer_id)
        ) or {
            "windy_layer": layer_id,
            "job": None,
            "current_job_updated": False,
        }
        listener.control_set_post_type = lambda post_type: calls.append(
            ("post_type", post_type)
        ) or {
            "post_type": post_type,
            "job": {
                "post_type": post_type,
                "captions": {"facebook": "Preview"},
            },
        }
        listener.get_current_job = lambda: {
            "job_id": "intent-job",
            "status": "pending",
            "post_type": "image",
            "available_post_types": ["image", "text"],
        }

        explicit_cases = [
            (
                listener.image_fit_intent_command("smartfit"),
                ("image_fit", "smartfit"),
            ),
            (
                listener.image_fit_intent_command("crop"),
                ("image_fit", "crop"),
            ),
            (
                listener.image_fit_intent_command("stretch"),
                ("image_fit", "stretch"),
            ),
            (
                listener.windy_layer_intent_command("satellite"),
                ("windy_layer", "satellite"),
            ),
            (
                listener.windy_layer_intent_command("radar"),
                ("windy_layer", "radar"),
            ),
            (
                listener.post_type_intent_command("text"),
                ("post_type", "text"),
            ),
        ]

        for handler, expected_call in explicit_cases:
            update = FakeUpdate()
            await handler(update, FakeContext())
            assert calls[-1] == expected_call
            assert update.message.replies

        deprecated_cases = [
            (
                listener.image_fit_command,
                FakeContext(["smartfit"]),
                "/image_fit_smartfit",
            ),
            (
                listener.windy_layer_command,
                FakeContext(["wind"]),
                "/windy_layer_wind",
            ),
            (
                listener.post_type_command,
                FakeContext(["image"]),
                "/post_type_image",
            ),
        ]
        for handler, context, replacement in deprecated_cases:
            update = FakeUpdate()
            await handler(update, context)
            reply = "\n".join(update.message.replies)
            assert "deprecated" in reply.casefold()
            assert replacement in reply
    finally:
        listener.set_fit_mode = original_fit
        listener.control_set_windy_layer = original_windy
        listener.control_set_post_type = original_post_type
        listener.get_current_job = original_get_job


def verify_command_maps_and_manuals():
    assert listener.IMAGE_FIT_INTENTS == {
        "image_fit_stretch": "stretch",
        "image_fit_smartfit": "smartfit",
        "image_fit_crop": "crop",
    }
    assert listener.WINDY_LAYER_INTENTS["windy_layer_satellite"] == "satellite"
    assert listener.WINDY_LAYER_INTENTS["windy_layer_radar"] == "radar"
    assert listener.POST_TYPE_INTENTS == {
        "post_type_image": "image",
        "post_type_text": "text",
    }

    manuals = "\n".join([
        inspect.getsource(listener.manual_command),
        inspect.getsource(listener.image_manual_command),
        inspect.getsource(listener.windy_manual_command),
    ])
    for command in (
        "/image_fit_smartfit",
        "/image_fit_crop",
        "/image_fit_stretch",
        "/windy_layer_satellite",
        "/windy_layer_radar",
        "/windy_layer_wind",
        "/post_type_image",
        "/post_type_text",
    ):
        assert command in manuals


def main():
    verify_command_maps_and_manuals()
    asyncio.run(verify_handlers())
    print("Telegram intent command verification ok")


if __name__ == "__main__":
    main()
