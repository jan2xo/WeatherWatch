import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_editorial_fallback import (
    AIEditorialUnavailable,
    generate_with_fallback,
    validate_factual_claims,
)


class BrokenProvider:
    name = "broken"

    def generate(self, context):
        raise TimeoutError("simulated timeout")


class SafeProvider:
    name = "safe"

    def generate(self, context):
        return {
            "headline": "Winds at 95 km/h",
            "caption": "PAGASA reports winds at 95 km/h.",
            "generation_mode": "ai_assisted",
            "model": "safe-model",
        }


class UnsafeProvider:
    name = "unsafe"

    def generate(self, context):
        return {
            "headline": "Winds at 120 km/h",
            "caption": "Winds at 120 km/h.",
            "generation_mode": "ai_assisted",
            "model": "unsafe-model",
        }


def verify_fallback_and_provenance():
    draft, provenance = generate_with_fallback(
        [BrokenProvider(), SafeProvider()],
        {"weather_facts": {"maximum_sustained_winds_kmh": 95}},
    )
    assert draft.provider == "safe"
    assert draft.fallback_level == 1
    assert provenance.provider == "safe"
    assert provenance.validation_state == "valid"


def verify_unsupported_measurement_is_rejected():
    result = validate_factual_claims(
        UnsafeProvider().generate({"weather_facts": {}}) and
        __import__(
            "services.ai_editorial_service",
            fromlist=["validate_editorial_output"],
        ).validate_editorial_output(
            UnsafeProvider().generate({}),
            provider="unsafe",
            model="unsafe-model",
        ),
        {"maximum_sustained_winds_kmh": 95},
    )
    assert result.state == "invalid"
    assert "120 km/h" in result.reasons[0]


def verify_all_failed_is_explicit():
    try:
        generate_with_fallback(
            [BrokenProvider(), UnsafeProvider()],
            {"weather_facts": {"maximum_sustained_winds_kmh": 95}},
        )
    except AIEditorialUnavailable as error:
        assert "unavailable/degraded" in str(error)
    else:
        raise AssertionError("All unsafe/unavailable providers must fail safely")


if __name__ == "__main__":
    verify_fallback_and_provenance()
    verify_unsupported_measurement_is_rejected()
    verify_all_failed_is_explicit()
    print("AI fallback and provenance verification ok")
