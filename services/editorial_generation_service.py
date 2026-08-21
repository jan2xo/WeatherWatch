"""Operational AI editorial generation around the existing provider contract."""

from datetime import datetime, timezone

from services.ai_config_service import get_enabled_provider_configs
from services.ai_editorial_fallback import (
    AIEditorialUnavailable,
    generate_with_fallback,
)
from services.ai_provider_adapters import build_provider_from_config
from services.editorial_context_service import build_editorial_context


def _memory_tags(facts):
    tags = []
    for key in ("affected_weather_system", "weather_type", "cyclone_classification"):
        value = facts.get(key)
        if value:
            tags.append(str(value))
    tags.extend(str(item) for item in facts.get("affected_areas", []) if item)
    return tags


def generate_ai_editorial(facts):
    context = build_editorial_context(facts, memory_tags=_memory_tags(facts))
    providers = []
    unavailable = []
    for config in get_enabled_provider_configs():
        try:
            providers.append(build_provider_from_config(config))
        except Exception as error:
            unavailable.append(f"{config['name']}: {error}")
    if not providers:
        raise AIEditorialUnavailable(
            "AI ASSISTED unavailable/degraded; no configured provider is ready. "
            + " | ".join(unavailable)
        )

    draft, provenance = generate_with_fallback(providers, context)
    return draft, {
        "generation_mode": provenance.generation_mode,
        "provider": provenance.provider,
        "model": provenance.model,
        "fallback_level": provenance.fallback_level,
        "validation_state": provenance.validation_state,
        "validation_reasons": list(provenance.validation_reasons),
        "memory_references": list(provenance.memory_references),
        "rules_version": context["rules_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
