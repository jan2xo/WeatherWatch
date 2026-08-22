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
    "approved": true,
    "created_at": "2026-08-22T12:00:00+08:00",
    "updated_at": "2026-08-22T12:00:00+08:00",
    "headline": "PAG-ULAN, ASAHAN SA ILANG BAHAGI NG CAGAYAN",
    "caption": "Approved WeatherWatch wording goes here.",
    "tags": ["rain", "cagayan", "advisory"],
    "category": "rain_advisory",
    "locations": ["Cagayan"],
    "tone": "calm",
    "source_type": "owner_curated"
  }
]
```

Required fields are `memory_id`, `approved`, `created_at`, `updated_at`,
`headline`, `caption`, `tags`, `category`, `locations`, `tone`, and
`source_type`. Optional fields are `text` and `post_type`. IDs are stable,
unique, lowercase identifiers; timestamps must be ISO 8601 with a timezone and
`updated_at` cannot precede `created_at`. Only explicitly approved items are
eligible. Retrieval is bounded to at most ten examples. Memory is editorial
precedent, never meteorological truth, and human edits do not enter the corpus
automatically.

The active managed-runtime corpus is rooted beneath
`WEATHERWATCH_RUNTIME_ROOT`; the repository file seeds it only when no runtime
copy exists. Validate before deployment or reload, without contacting any
provider:

```bash
python -m tools.editorial_memory schema
python -m tools.editorial_memory validate
python -m tools.editorial_memory validate /path/to/editorial_memory.json
```

The owner or designated editor must replace the empty corpus with real approved
examples. Synthetic fixtures are verification data, not production memory.

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

Runtime environment overrides support enabled state, model, and timeout for
each named provider, for example
`WEATHERWATCH_AI_OPENROUTER_ENABLED`,
`WEATHERWATCH_AI_OPENROUTER_MODEL`, and
`WEATHERWATCH_AI_OPENROUTER_TIMEOUT_SECONDS`, with equivalent `PROVIDER_2`,
`PROVIDER_3`, and `OPENAI` names shown in `.env.example`. Provider priority and
credential-reference names remain repository-controlled; endpoints, models,
and keys remain owner-controlled. Missing endpoint/model/key makes that provider
unavailable without exposing its credential.

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

Repository tests use fake adapters only. Actual provider/model/key selection,
live fallback behavior, latency, quotas, and output certification remain
owner-controlled runtime work.
