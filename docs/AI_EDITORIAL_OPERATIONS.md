# AI Editorial Operations

P13 turns the existing provider-neutral AI and memory scaffolding into an
operational, optional editorial path. The deterministic `TEMPLATED` composer
remains the fallback and does not call providers.

## Owner-managed corpus

Add approved WeatherWatch examples to `config/editorial_memory.json`. The file
is a JSON array with stable IDs, for example:

```json
[
  {
    "memory_id": "rain-cagayan-001",
    "headline": "PAG-ULAN, ASAHAN SA ILANG BAHAGI NG CAGAYAN",
    "caption": "Approved WeatherWatch wording goes here.",
    "tags": ["rain", "cagayan", "advisory"],
    "category": "rain_advisory",
    "approved": true,
    "source_type": "curated"
  }
]
```

Only explicitly approved items are eligible. Retrieval is bounded to five
examples by default. Memory is editorial precedent, never meteorological
truth, and human edits do not enter the corpus automatically.

## Context and rules

`services/editorial_context_service.py` assembles canonical structured facts,
`config/editorial_rules.json`, a bounded memory subset, factual constraints,
and the structured output schema. The rules file has a version recorded in
AI provenance.

## Provider configuration

`config/ai_editorial.json` controls mode, enabled state, priority, model,
timeout, and credential environment-variable reference. Provider credentials
are resolved only from runtime environment secrets. The default providers are
disabled and the default mode is `templated`.

The implemented adapters are OpenRouter and OpenAI plus generic OpenAI-compatible
adapters for configured `provider_2` and `provider_3` endpoints. Their model
inventories are not hardcoded. Configure endpoints through:

- `OPENROUTER_BASE_URL` / `OPENROUTER_API_KEY`
- `AI_PROVIDER_2_BASE_URL` / `AI_PROVIDER_2_API_KEY`
- `AI_PROVIDER_3_BASE_URL` / `AI_PROVIDER_3_API_KEY`
- `OPENAI_BASE_URL` / `OPENAI_API_KEY`

No credential values belong in the repository.

## Runtime behavior

- `templated`: deterministic composer only.
- `ai_assisted`: configured AI chain, with visible degraded status when it is
  unavailable; no AI output is mislabeled.
- `automatic`: configured AI chain first, then deterministic TEMPLATED output
  if every provider fails or produces invalid output.

Every successful AI draft records provider, model, fallback level, validation
state, rules version, memory references, and timestamp in the approval job
without storing secrets or raw provider payloads.

Telegram `/ai_status` shows safe configuration and current generation metadata;
`/memory_status` shows corpus/rules counts without exposing credentials or
prompts. Existing approval, dashboard, CLI/headless, rendering, Facebook, and
VPS interfaces remain in place.

