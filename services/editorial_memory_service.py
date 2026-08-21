"""Curated editorial-memory boundary for future AI context assembly.

Memory is editorial precedent only. This module does not provide weather facts,
does not persist data, and never replaces the canonical forecast.
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EditorialMemoryItem:
    memory_id: str
    text: str
    tags: frozenset[str]
    approved: bool = True


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
