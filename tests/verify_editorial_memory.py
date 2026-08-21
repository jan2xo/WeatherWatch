import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.editorial_memory_service import (
    EditorialMemoryItem,
    retrieve_relevant_memory,
)


def verify_approved_relevant_subset():
    items = [
        EditorialMemoryItem("luzon-rain", "Rain wording", frozenset({"luzon", "rain"})),
        EditorialMemoryItem("storm", "Storm wording", frozenset({"storm"})),
        EditorialMemoryItem("rejected", "Do not use", frozenset({"luzon"}), approved=False),
    ]
    selected = retrieve_relevant_memory(
        items,
        tags=["Luzon", "rain"],
        limit=2,
    )
    assert [item.memory_id for item in selected] == ["luzon-rain", "storm"]


def verify_limit_and_determinism():
    items = [
        EditorialMemoryItem("b", "B", frozenset({"weather"})),
        EditorialMemoryItem("a", "A", frozenset({"weather"})),
    ]
    selected = retrieve_relevant_memory(items, tags=["weather"], limit=1)
    assert [item.memory_id for item in selected] == ["a"]


def verify_invalid_limit():
    try:
        retrieve_relevant_memory([], limit=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative memory limit must fail")


if __name__ == "__main__":
    verify_approved_relevant_subset()
    verify_limit_and_determinism()
    verify_invalid_limit()
    print("editorial memory verification ok")
