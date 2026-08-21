"""Provider-independent WeatherWatch editorial context assembly."""

import json
from pathlib import Path

from services.editorial_memory_service import (
    DEFAULT_MEMORY_PATH,
    load_editorial_memory,
    memory_item_to_context,
    retrieve_relevant_memory,
)


RULES_PATH = Path("config/editorial_rules.json")
DEFAULT_MEMORY_LIMIT = 5


def load_editorial_rules(path=RULES_PATH):
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or not isinstance(rules.get("rules"), list):
        raise ValueError("Editorial rules must contain a rules array.")
    if not rules.get("version"):
        raise ValueError("Editorial rules require a version.")
    if any(not isinstance(rule, str) or not rule.strip() for rule in rules["rules"]):
        raise ValueError("Editorial rules must contain non-empty strings.")
    return rules


def build_editorial_context(
    canonical_facts,
    *,
    memory_tags=(),
    memory_path=DEFAULT_MEMORY_PATH,
    rules_path=RULES_PATH,
    memory_limit=DEFAULT_MEMORY_LIMIT,
):
    if not isinstance(canonical_facts, dict):
        raise ValueError("Canonical weather facts must be an object.")
    if memory_limit < 0 or memory_limit > 10:
        raise ValueError("Editorial memory limit must be between 0 and 10.")
    rules = load_editorial_rules(rules_path)
    corpus = load_editorial_memory(memory_path)
    selected = retrieve_relevant_memory(corpus, tags=memory_tags, limit=memory_limit)
    return {
        "weather_facts": canonical_facts,
        "editorial_rules": list(rules["rules"]),
        "rules_version": rules["version"],
        "memory_examples": [memory_item_to_context(item) for item in selected],
        "memory_references": [item.memory_id for item in selected],
        "output_schema": rules.get("output_schema", {
            "headline": "string",
            "caption": "string",
            "generation_mode": "ai_assisted",
            "memory_references": "array of memory IDs",
        }),
        "factual_constraints": {
            "canonical_facts_are_authoritative": True,
            "memory_is_editorial_precedent_only": True,
            "unsupported_claims_must_be_rejected": True,
        },
    }
