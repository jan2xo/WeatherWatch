import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import editorial_generation_service as generation
from services.ai_editorial_fallback import AIEditorialUnavailable


class FakeProvider:
    def __init__(self, name, payload=None, error=None):
        self.name = name
        self.payload = payload
        self.error = error
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        if self.error:
            raise self.error
        return dict(self.payload)


def _context(facts):
    return {
        "weather_facts": facts,
        "editorial_rules": ["No inventions"],
        "rules_version": "test",
        "memory_examples": [],
        "memory_references": [],
        "output_schema": {},
        "factual_constraints": {},
    }


def main():
    facts = {
        "affected_weather_system": "Southwest Monsoon",
        "affected_areas": ["Cagayan"],
        "maximum_sustained_winds_kmh": 80,
    }
    original_build = generation.build_provider_from_config
    original_context = generation.build_editorial_context
    original_configs = generation.get_enabled_provider_configs
    try:
        generation.build_editorial_context = lambda facts, **_: _context(facts)
        providers = [
            FakeProvider("openrouter", error=TimeoutError("timeout")),
            FakeProvider("provider_2", error=RuntimeError("quota")),
            FakeProvider("provider_3", payload={
                "headline": "Validated headline",
                "caption": "Winds reach 80 km/h.",
                "generation_mode": "ai_assisted",
                "model": "free-model",
            }),
        ]
        by_name = {item.name: item for item in providers}
        generation.get_enabled_provider_configs = lambda: tuple({
            "name": item.name,
            "model": "free-model",
            "timeout_seconds": 2,
            "credential_reference": "SYNTHETIC_KEY",
        } for item in providers)
        generation.build_provider_from_config = lambda config: by_name[config["name"]]
        draft, provenance = generation.generate_ai_editorial(facts)
        assert draft.provider == "provider_3"
        assert provenance["fallback_level"] == 2
        assert provenance["rules_version"] == "test"

        provider_2 = FakeProvider("provider_2", payload={
            "headline": "Validated headline",
            "caption": "Winds reach 80 km/h.",
            "generation_mode": "ai_assisted",
            "model": "free-model",
        })
        generation.get_enabled_provider_configs = lambda: (
            {"name": "openrouter", "model": "free-model", "timeout_seconds": 2, "credential_reference": "SYNTHETIC_KEY"},
            {"name": "provider_2", "model": "free-model", "timeout_seconds": 2, "credential_reference": "SYNTHETIC_KEY"},
        )

        def build_with_unavailable_primary(config):
            if config["name"] == "openrouter":
                raise RuntimeError("endpoint not configured")
            return provider_2

        generation.build_provider_from_config = build_with_unavailable_primary
        draft, provenance = generation.generate_ai_editorial(facts)
        assert draft.provider == "provider_2"
        assert provenance["fallback_level"] == 1

        generation.get_enabled_provider_configs = lambda: ()
        try:
            generation.generate_ai_editorial(facts)
        except AIEditorialUnavailable:
            pass
        else:
            raise AssertionError("No providers must be visibly unavailable")
    finally:
        generation.build_provider_from_config = original_build
        generation.build_editorial_context = original_context
        generation.get_enabled_provider_configs = original_configs
    print("live editorial generation verification ok")


if __name__ == "__main__":
    main()
