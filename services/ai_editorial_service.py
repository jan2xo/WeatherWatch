"""Provider-neutral contract for future AI-assisted editorial generation.

This module is additive. It does not call providers, alter TEMPLATED
composition, or publish content. Future adapters can implement the
EditorialProvider protocol and return a validated AIEditorialDraft.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


GENERATION_MODE = "ai_assisted"
VALIDATION_PENDING = "pending"
VALIDATION_VALID = "valid"


class AIEditorialError(ValueError):
    """Base error for invalid AI editorial contracts."""


class AIEditorialOutputError(AIEditorialError):
    """Raised when a provider response violates the output contract."""


@dataclass(frozen=True)
class AIEditorialDraft:
    headline: str
    caption: str
    generation_mode: str
    provider: str
    model: str
    validation_state: str = VALIDATION_VALID
    fallback_level: int | None = None
    memory_references: tuple[str, ...] = ()


class EditorialProvider(Protocol):
    """Minimal provider boundary; provider SDK details stay outside WeatherWatch."""

    name: str

    def generate(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AIEditorialOutputError(
            f"AI editorial output field {field!r} must be a non-empty string."
        )
    return value.strip()


def validate_editorial_output(
    payload: Mapping[str, Any],
    *,
    provider: str,
    model: str,
    validation_state: str = VALIDATION_VALID,
    fallback_level: int | None = None,
) -> AIEditorialDraft:
    """Validate the provider-neutral structured output contract.

    Factual validation against canonical weather facts belongs to the next
    bounded phase. This function only prevents malformed provider prose from
    entering the editorial workflow.
    """

    if not isinstance(payload, Mapping):
        raise AIEditorialOutputError("AI editorial output must be an object.")

    if not isinstance(provider, str) or not provider.strip():
        raise AIEditorialOutputError("AI provider identity is required.")

    if not isinstance(model, str) or not model.strip():
        raise AIEditorialOutputError("AI model identity is required.")

    mode = payload.get("generation_mode", GENERATION_MODE)
    if mode != GENERATION_MODE:
        raise AIEditorialOutputError(
            f"generation_mode must be {GENERATION_MODE!r}."
        )

    if validation_state not in {VALIDATION_PENDING, VALIDATION_VALID}:
        raise AIEditorialOutputError("Unsupported editorial validation state.")

    references = payload.get("memory_references", ())
    if isinstance(references, str) or not isinstance(references, (list, tuple)):
        raise AIEditorialOutputError("memory_references must be a list of IDs.")

    normalized_references = tuple(
        reference.strip()
        for reference in references
        if isinstance(reference, str) and reference.strip()
    )

    if len(normalized_references) != len(references):
        raise AIEditorialOutputError(
            "memory_references must contain only non-empty strings."
        )

    if fallback_level is not None and (
        not isinstance(fallback_level, int) or fallback_level < 0
    ):
        raise AIEditorialOutputError(
            "fallback_level must be a non-negative integer or None."
        )

    return AIEditorialDraft(
        headline=_required_text(payload, "headline"),
        caption=_required_text(payload, "caption"),
        generation_mode=mode,
        provider=provider.strip(),
        model=model.strip(),
        validation_state=validation_state,
        fallback_level=fallback_level,
        memory_references=normalized_references,
    )


class OrderedEditorialProviderRouter:
    """Configuration-driven provider order without provider-specific business logic."""

    def __init__(self, providers: list[EditorialProvider]):
        if not providers:
            raise ValueError("At least one editorial provider is required.")
        self._providers = tuple(providers)

    @property
    def providers(self) -> tuple[EditorialProvider, ...]:
        return self._providers

    def generate_from(self, index: int, context: Mapping[str, Any]):
        if index < 0 or index >= len(self._providers):
            raise IndexError("Provider index is outside the configured order.")

        provider = self._providers[index]
        payload = provider.generate(context)
        return validate_editorial_output(
            payload,
            provider=provider.name,
            model=str(payload.get("model", "")),
            fallback_level=index,
        )
