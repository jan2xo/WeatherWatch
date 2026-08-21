# WeatherWatch Editorial Domain Contract

Status: architecture boundary for the P1 roadmap lane
Baseline: `main@b5ba68da9ca234eeef7bdd4ca0bd336754c1a8b2`

This document records the current WeatherWatch boundary and the contract that future editorial work must preserve. It does not change runtime behavior. The existing job dictionary and approval workflow remain compatible while later bounded phases introduce explicit domain types or adapters.

## Authority and flow

```
authoritative weather source
        ↓
services/pagasa_service.py
        ↓
services/forecast_service.py / services/forecast_parser.py
        ↓
structured forecast facts
        ↓
services/content_composer_service.py
services/caption_template_service.py
        ↓
headline and captions
        ↓
image rendering and approval state
        ↓
human review
        ↓
Facebook publication
```

PAGASA or another configured authoritative source supplies meteorological information. WeatherWatch parses and normalizes that information. Editorial composition may phrase the information, but it must not become a second meteorological authority.

AI-assisted generation, when implemented, is an editorial writer. It receives controlled WeatherWatch facts and produces wording under an explicit output contract. It does not define weather systems, locations, warnings, measurements, storm state, dates, times, or source attribution.

## Contract layers

### 1. Source material

Source material is the externally retrieved input and attribution needed to reconstruct what WeatherWatch received.

Current repository fields include:

- `forecast_text`: fetched PAGASA synopsis or source text;
- `provider`, `provider_display`, `provider_url`, and `url`: source/provider identity and capture URL;
- `source`: public attribution text used by the current workflow.

Source material is evidence, not an editorial draft. It must not be silently replaced by generated wording.

### 2. Structured weather truth

Structured weather truth is the parsed and normalized representation used by WeatherWatch services.

The current implementation carries this through the `forecast` job field and the forecast/parser/composer services. The exact fields are implementation-owned and must be inspected before any future schema migration. Future work may formalize the contract, but must preserve the following semantic categories where present:

- weather systems and storm state;
- affected areas and locations;
- warnings or alert levels;
- rainfall, wind, and other measurements;
- dates and times;
- source attribution;
- parser/normalization outcomes and fallback information.

Canonical facts outrank editorial memory, provider prose, and AI output. A value not supported by the source or validated parser result must not be promoted to structured truth merely because an editor or model suggested it.

### 3. Editorial output

Editorial output is wording derived from structured facts and editorial rules.

The current workflow uses:

- `headline`: the graphic headline;
- `captions`: channel-specific output, including Facebook/Instagram wording;
- `caption`: compatibility field used by existing paths;
- content-composer and caption-template configuration.

TEMPLATED output is deterministic and remains usable with AI unavailable. Future AI ASSISTED output must use the same semantic editorial boundary, expose its generation mode, and be rejected when it does not satisfy its structured contract or factual validation.

Editorial output may be modified by a human. A human modification is not a change to the underlying meteorological facts.

### 4. Approval and publication state

Approval state controls workflow authority rather than weather truth or editorial content.

The current repository uses a singleton current job and history in `storage/approval_store.py`, with control-plane transitions for generation, approval, rejection, modification, retry, and publication. Current job fields include paths, provider/source data, forecast data, headline, captions, and status metadata.

Future durable-state work must preserve the distinction between:

- generated;
- modified;
- approved;
- publishing;
- posted;
- publish_failed;
- rejected or otherwise terminal history.

Approval is the human editorial gate. A generated or validated draft is not approved merely because it was produced successfully.

## Required invariants for future phases

1. The authoritative source and parsed weather facts remain distinguishable from editorial wording.
2. TEMPLATED remains a first-class deterministic mode and does not depend on AI providers.
3. AI ASSISTED output cannot overwrite canonical facts.
4. AI or memory cannot invent unsupported meteorological claims.
5. Human modification affects the editorial output selected for review/publication, not the canonical weather record.
6. Existing Telegram, dashboard, CLI/headless, rendering, Facebook, health, and VPS paths remain compatible.
7. Approval and publication state transitions remain explicit and attributable.
8. Provider/model/provenance fields may be added only through a bounded contract change and must not contain secrets.
9. Synthetic tests may surround the real parser, composer, rendering, approval, and publication subjects; they must not claim that mocked critical behavior executed.
10. This contract documents engineering certification scope. It is not production certification or deployment verification.

## Compatibility rule

This document is intentionally descriptive of the current implementation and normative for future changes. A future worker must inspect the current fields and tests before introducing typed models, persistence migrations, AI adapters, or UI changes. No implementation phase may infer missing weather facts or rewrite the existing approval workflow merely to fit this document.

## Verification expectation for this lane

P1 is complete when this boundary is reviewed against:

- `core/app.py`;
- `pipelines/weather_pipeline.py`;
- `services/forecast_parser.py`;
- `services/content_composer_service.py`;
- `services/caption_template_service.py`;
- `services/control_plane_service.py`;
- `storage/approval_store.py`;
- existing parser, composer, approval, rendering, Telegram, and dashboard tests.

This lane does not claim those tests were rerun by the documentation commit. Later implementation lanes must execute their applicable worker-loop and convergence verification.
