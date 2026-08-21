"""Fallback, factual-boundary, and provenance helpers for AI editorial drafts."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Sequence

from services.ai_editorial_service import (
    AIEditorialDraft,
    AIEditorialError,
    OrderedEditorialProviderRouter,
    validate_editorial_output,
)


NUMERIC_CLAIM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?)\s*"
    r"(?:km/h|kph|mm|°C|°|%|kilometers?\s*/\s*hour)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FactualValidationResult:
    state: str
    checked_claims: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorialProvenance:
    generation_mode: str
    provider: str
    model: str
    fallback_level: int
    validation_state: str
    validation_reasons: tuple[str, ...] = ()
    memory_references: tuple[str, ...] = ()


class AIEditorialUnavailable(RuntimeError):
    """All configured AI attempts failed or were rejected."""


def _walk_values(value: Any):
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _walk_values(nested)
    elif isinstance(value, (str, int, float)):
        yield str(value)


def _normalize_claim(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def _canonical_numeric_claims(value: Any, key: str = ""):
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            yield from _canonical_numeric_claims(nested_value, str(nested_key))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _canonical_numeric_claims(nested, key)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        key_units = {
            "kmh": "km/h",
            "km/h": "km/h",
            "mm": "mm",
            "c": "°C",
            "percent": "%",
        }
        normalized_key = key.casefold().replace("_", "")
        for marker, unit in key_units.items():
            if marker in normalized_key:
                yield f"{value:g} {unit}"
                break


def validate_factual_claims(
    draft: AIEditorialDraft,
    canonical_facts: Mapping[str, Any],
) -> FactualValidationResult:
    """Conservatively reject measurable claims absent from canonical facts.

    This is intentionally not a general meteorological model. It validates
    explicit numeric/unit claims that can be compared safely from current
    structured facts. Future parser-specific validators may extend it for
    locations, warnings, dates, and systems without weakening this boundary.
    """

    if not isinstance(canonical_facts, Mapping):
        return FactualValidationResult(
            state="invalid",
            reasons=("canonical facts must be a mapping",),
        )

    canonical_claims = {
        _normalize_claim(claim)
        for value in _walk_values(canonical_facts)
        for claim in NUMERIC_CLAIM_PATTERN.findall(value)
    }
    canonical_claims.update(
        _normalize_claim(claim)
        for claim in _canonical_numeric_claims(canonical_facts)
    )
    output_text = f"{draft.headline}\n{draft.caption}"
    output_claims = tuple(
        match.group(0)
        for match in NUMERIC_CLAIM_PATTERN.finditer(output_text)
    )

    unsupported = tuple(
        claim for claim in output_claims
        if _normalize_claim(claim) not in canonical_claims
    )
    if unsupported:
        return FactualValidationResult(
            state="invalid",
            checked_claims=output_claims,
            reasons=tuple(
                f"unsupported measurable claim: {claim}"
                for claim in unsupported
            ),
        )

    if output_claims:
        return FactualValidationResult(
            state="valid",
            checked_claims=output_claims,
        )

    return FactualValidationResult(
        state="partial",
        reasons=("no measurable claim was available for comparison",),
    )


def generate_with_fallback(
    providers: Sequence,
    context: Mapping[str, Any],
    *,
    factual_validator: Callable[
        [AIEditorialDraft, Mapping[str, Any]], FactualValidationResult
    ] = validate_factual_claims,
):
    """Try configured providers in order and return the first safe draft."""

    router = OrderedEditorialProviderRouter(list(providers))
    attempts = []

    for index, provider in enumerate(router.providers):
        try:
            payload = provider.generate(context)
            draft = validate_editorial_output(
                payload,
                provider=provider.name,
                model=str(payload.get("model", "")),
                fallback_level=index,
            )
            selected_memory = set(context.get("memory_references", ()))
            if any(reference not in selected_memory for reference in draft.memory_references):
                raise AIEditorialError("AI output referenced memory outside the selected context.")
            facts = context.get("weather_facts", {})
            factual = factual_validator(draft, facts)
            if factual.state != "valid":
                raise AIEditorialError("; ".join(factual.reasons) or factual.state)

            provenance = EditorialProvenance(
                generation_mode=draft.generation_mode,
                provider=draft.provider,
                model=draft.model,
                fallback_level=index,
                validation_state=factual.state,
                validation_reasons=factual.reasons,
                memory_references=draft.memory_references or tuple(
                    context.get("memory_references", ())
                ),
            )
            return draft, provenance
        except Exception as error:
            attempts.append(f"{getattr(provider, 'name', 'unknown')}: {error}")

    raise AIEditorialUnavailable(
        "AI ASSISTED unavailable/degraded; attempts: " + " | ".join(attempts)
    )
