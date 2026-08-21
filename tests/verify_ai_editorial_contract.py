import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_editorial_service import (
    AIEditorialOutputError,
    OrderedEditorialProviderRouter,
    validate_editorial_output,
)


class Provider:
    name = "test-provider"

    def generate(self, context):
        return {
            "headline": "Rain expected",
            "caption": "A controlled editorial draft.",
            "generation_mode": "ai_assisted",
            "model": "test-model",
            "memory_references": ["example-1"],
        }


def verify_valid_output():
    draft = validate_editorial_output(
        {
            "headline": "Rain expected",
            "caption": "A controlled editorial draft.",
            "generation_mode": "ai_assisted",
            "memory_references": ["example-1"],
        },
        provider="test-provider",
        model="test-model",
    )
    assert draft.generation_mode == "ai_assisted"
    assert draft.provider == "test-provider"
    assert draft.memory_references == ("example-1",)


def verify_malformed_output_rejected():
    cases = [
        {},
        {"headline": "Only headline"},
        {"headline": "Headline", "caption": "Caption", "generation_mode": "templated"},
        {"headline": "Headline", "caption": "Caption", "memory_references": [""]},
    ]
    for payload in cases:
        try:
            validate_editorial_output(
                payload,
                provider="test-provider",
                model="test-model",
            )
        except AIEditorialOutputError:
            continue
        raise AssertionError("Malformed AI output must be rejected")


def verify_router_preserves_order_and_metadata():
    draft = OrderedEditorialProviderRouter([Provider()]).generate_from(
        0,
        {"weather_facts": {"source": "PAGASA"}},
    )
    assert draft.provider == "test-provider"
    assert draft.model == "test-model"
    assert draft.fallback_level == 0


if __name__ == "__main__":
    verify_valid_output()
    verify_malformed_output_rejected()
    verify_router_preserves_order_and_metadata()
    print("AI editorial contract verification ok")
