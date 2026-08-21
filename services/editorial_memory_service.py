"""Curated editorial-memory store and bounded retrieval.

Memory is editorial precedent only. This module does not provide weather facts,
does not persist data, and never replaces the canonical forecast.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


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


DEFAULT_MEMORY_PATH = Path("config/editorial_memory.json")


def _text(value, field, *, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"Memory {field} must be a string.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Memory {field} is required.")
    return value


def load_editorial_memory(path=DEFAULT_MEMORY_PATH):
    """Load the owner-curated corpus; invalid input fails closed."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Editorial memory corpus must be a JSON array.")

    items = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each editorial memory item must be an object.")
        memory_id = _text(entry.get("memory_id"), "memory_id", required=True)
        if memory_id in seen:
            raise ValueError("Editorial memory IDs must be unique.")
        seen.add(memory_id)
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("Memory tags must be a list of strings.")
        locations = entry.get("locations", [])
        if not isinstance(locations, list) or any(not isinstance(item, str) for item in locations):
            raise ValueError("Memory locations must be a list of strings.")
        approved = entry.get("approved", False)
        if not isinstance(approved, bool):
            raise ValueError("Memory approved must be boolean.")
        headline = _text(entry.get("headline"), "headline")
        caption = _text(entry.get("caption"), "caption")
        text = _text(entry.get("text"), "text") or "\n".join(
            value for value in (headline, caption) if value
        )
        items.append(EditorialMemoryItem(
            memory_id=memory_id,
            text=text,
            tags=frozenset(tag.strip() for tag in tags if tag.strip()),
            approved=approved,
            headline=headline,
            caption=caption,
            category=_text(entry.get("category"), "category"),
            post_type=_text(entry.get("post_type"), "post_type"),
            locations=tuple(item.strip() for item in locations if item.strip()),
            tone=_text(entry.get("tone"), "tone"),
            source_type=_text(entry.get("source_type"), "source_type") or "curated",
            created_at=_text(entry.get("created_at"), "created_at"),
            updated_at=_text(entry.get("updated_at"), "updated_at"),
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

    if limit < 0:
        raise ValueError("limit must be non-negative")

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
