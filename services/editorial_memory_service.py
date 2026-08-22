"""Curated editorial-memory store and bounded retrieval.

Memory is editorial precedent only. This module does not provide weather facts,
does not persist data, and never replaces the canonical forecast.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config.runtime_paths import runtime_config_path


@dataclass(frozen=True)
class EditorialMemoryItem:
    memory_id: str
    text: str
    tags: frozenset[str]
    approved: bool = True
    headline: str = ""
    caption: str = ""
    category: str = ""
    post_type: str = ""
    locations: tuple[str, ...] = ()
    tone: str = ""
    source_type: str = "curated"
    created_at: str = ""
    updated_at: str = ""


DEFAULT_MEMORY_PATH = runtime_config_path("config/editorial_memory.json")
MEMORY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
MAX_RETRIEVAL_LIMIT = 10
OPERATOR_REQUIRED_FIELDS = frozenset({
    "memory_id",
    "approved",
    "created_at",
    "updated_at",
    "headline",
    "caption",
    "tags",
    "category",
    "locations",
    "tone",
    "source_type",
})
OPERATOR_OPTIONAL_FIELDS = frozenset({"text", "post_type"})


def _text(value, field, *, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"Memory {field} must be a string.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Memory {field} is required.")
    return value


def _iso_timestamp(value, field, *, required=False):
    text = _text(value, field, required=required)
    if not text:
        return "", None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Memory {field} must be an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Memory {field} must include a timezone.")
    return text, parsed.astimezone(timezone.utc)


def _load_raw_corpus(path):
    resolved = Path(path)
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Editorial memory corpus must be a JSON array.")
    return raw


def _validate_string_list(value, field, *, required=False):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Memory {field} must be a list of strings.")
    normalized = tuple(item.strip() for item in value if item.strip())
    if len(normalized) != len(value):
        raise ValueError(f"Memory {field} must contain only non-empty strings.")
    if required and not normalized:
        raise ValueError(f"Memory {field} requires at least one value.")
    if len(set(item.casefold() for item in normalized)) != len(normalized):
        raise ValueError(f"Memory {field} must not contain duplicates.")
    return normalized


def validate_operator_memory_entry(entry):
    """Validate one complete owner-curated sample without changing the corpus."""

    if not isinstance(entry, dict):
        raise ValueError("Each editorial memory item must be an object.")
    missing = sorted(OPERATOR_REQUIRED_FIELDS - entry.keys())
    if missing:
        raise ValueError(
            "Editorial memory item is missing required fields: " + ", ".join(missing)
        )
    unknown = sorted(entry.keys() - OPERATOR_REQUIRED_FIELDS - OPERATOR_OPTIONAL_FIELDS)
    if unknown:
        raise ValueError(
            "Editorial memory item contains unsupported fields: " + ", ".join(unknown)
        )

    memory_id = _text(entry.get("memory_id"), "memory_id", required=True)
    if not MEMORY_ID_PATTERN.fullmatch(memory_id):
        raise ValueError(
            "Memory memory_id must use lowercase letters, numbers, dots, hyphens, or underscores."
        )
    if not isinstance(entry.get("approved"), bool):
        raise ValueError("Memory approved must be boolean.")
    _text(entry.get("headline"), "headline", required=True)
    _text(entry.get("caption"), "caption", required=True)
    _validate_string_list(entry.get("tags"), "tags", required=True)
    _text(entry.get("category"), "category", required=True)
    _validate_string_list(entry.get("locations"), "locations", required=True)
    _text(entry.get("tone"), "tone", required=True)
    _text(entry.get("source_type"), "source_type", required=True)
    created_text, created = _iso_timestamp(
        entry.get("created_at"), "created_at", required=True
    )
    updated_text, updated = _iso_timestamp(
        entry.get("updated_at"), "updated_at", required=True
    )
    if updated < created:
        raise ValueError("Memory updated_at must not be earlier than created_at.")
    return {
        "memory_id": memory_id,
        "approved": entry["approved"],
        "created_at": created_text,
        "updated_at": updated_text,
    }


def validate_editorial_memory_operations(path=DEFAULT_MEMORY_PATH):
    raw = _load_raw_corpus(path)
    seen = set()
    approved = 0
    for entry in raw:
        summary = validate_operator_memory_entry(entry)
        memory_id = summary["memory_id"]
        if memory_id in seen:
            raise ValueError("Editorial memory IDs must be unique.")
        seen.add(memory_id)
        approved += int(summary["approved"])
    return {
        "path": str(path),
        "validation_status": "valid",
        "items": len(raw),
        "approved_items": approved,
    }


def get_editorial_memory_operator_schema():
    return {
        "format": "JSON array",
        "required_fields": sorted(OPERATOR_REQUIRED_FIELDS),
        "optional_fields": sorted(OPERATOR_OPTIONAL_FIELDS),
        "memory_id": "stable lowercase identifier: [a-z0-9][a-z0-9._-]{0,127}",
        "timestamps": "ISO 8601 with timezone; updated_at >= created_at",
        "retrieval_limit": MAX_RETRIEVAL_LIMIT,
        "weather_authority": "canonical structured weather facts, never memory",
    }


def load_editorial_memory(path=DEFAULT_MEMORY_PATH):
    """Load the owner-curated corpus; invalid input fails closed."""
    raw = _load_raw_corpus(path)

    items = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each editorial memory item must be an object.")
        memory_id = _text(entry.get("memory_id"), "memory_id", required=True)
        if not MEMORY_ID_PATTERN.fullmatch(memory_id):
            raise ValueError("Memory memory_id must be a stable lowercase identifier.")
        if memory_id in seen:
            raise ValueError("Editorial memory IDs must be unique.")
        seen.add(memory_id)
        tags = _validate_string_list(entry.get("tags", []), "tags")
        locations = _validate_string_list(entry.get("locations", []), "locations")
        approved = entry.get("approved", False)
        if not isinstance(approved, bool):
            raise ValueError("Memory approved must be boolean.")
        headline = _text(entry.get("headline"), "headline")
        caption = _text(entry.get("caption"), "caption")
        text = _text(entry.get("text"), "text") or "\n".join(
            value for value in (headline, caption) if value
        )
        created_at, _ = _iso_timestamp(entry.get("created_at"), "created_at")
        updated_at, _ = _iso_timestamp(entry.get("updated_at"), "updated_at")
        items.append(EditorialMemoryItem(
            memory_id=memory_id,
            text=text,
            tags=frozenset(tags),
            approved=approved,
            headline=headline,
            caption=caption,
            category=_text(entry.get("category"), "category"),
            post_type=_text(entry.get("post_type"), "post_type"),
            locations=locations,
            tone=_text(entry.get("tone"), "tone"),
            source_type=_text(entry.get("source_type"), "source_type") or "curated",
            created_at=created_at,
            updated_at=updated_at,
        ))
    return tuple(items)


def memory_item_to_context(item):
    return {
        "memory_id": item.memory_id,
        "headline": item.headline,
        "caption": item.caption,
        "text": item.text,
        "tags": sorted(item.tags),
        "category": item.category,
        "post_type": item.post_type,
        "locations": list(item.locations),
        "tone": item.tone,
        "source_type": item.source_type,
    }


def retrieve_relevant_memory(
    items: Iterable[EditorialMemoryItem],
    *,
    tags: Iterable[str] = (),
    limit: int = 5,
) -> tuple[EditorialMemoryItem, ...]:
    """Return a small approved subset ranked by tag overlap.

    Callers must supply canonical weather facts separately. Memory is never
    treated as a source of meteorological truth.
    """

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer")
    if limit < 0 or limit > MAX_RETRIEVAL_LIMIT:
        raise ValueError(
            f"limit must be between 0 and {MAX_RETRIEVAL_LIMIT}"
        )

    requested = {
        str(tag).strip().casefold()
        for tag in tags
        if str(tag).strip()
    }
    candidates = []
    for item in items:
        if not item.approved:
            continue
        normalized_tags = {
            str(tag).strip().casefold()
            for tag in item.tags
            if str(tag).strip()
        }
        overlap = len(requested & normalized_tags)
        candidates.append((overlap, item.memory_id, item))

    candidates.sort(key=lambda row: (-row[0], row[1]))
    return tuple(item for _, _, item in candidates[:limit])
