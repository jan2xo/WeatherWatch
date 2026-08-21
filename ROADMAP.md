# WeatherWatch Roadmap

Version: 1.0 planning baseline
Planning branch: `docs/weatherwatch-editorial-ai-runtime-roadmap`
Base `main`: `bc29311a55f5d8b30941a5d209826ad8ec520be0`

This roadmap is a planning document. It does not authorize feature implementation by itself. Each implementation lane requires an approved bounded task, repository inspection, worker-loop verification, independent review, and the applicable convergence or certification gate.

## Product north star

WeatherWatch is a parser, normalizer, workflow owner, and publication system around authoritative weather information.

```
PAGASA / authoritative source
        ↓
deterministic ingestion
        ↓
forecast parsing and normalization
        ↓
structured weather truth
        ↓
templated or AI-assisted editorial layer
        ↓
human review
        ↓
Facebook publication
```

PAGASA remains the meteorological authority. WeatherWatch owns ingestion, parsing, normalization, editorial workflow, rendering, approval, and publication. AI is an editorial writer, not a weather authority. Human approval remains the final editorial authority.

Existing CLI/headless operation, Telegram approval, local dashboard, health/status behavior, rendering, Facebook publishing, and VPS support are preserved. Render is an additional runtime target to evaluate, not an automatic replacement.

## Repository reality baseline

The current repository is a Python modular service application.

- `main.py` starts `WeatherWatchService`; `python -m core.service` is the documented production entry point.
- `core/app.py` orchestrates updates, provider selection, PAGASA fetch, and the weather pipeline.
- `core/service.py` starts Telegram polling, scheduler, local admin dashboard, and Facebook reconnect support.
- `core/telegram_listener.py` is a substantial command router and human approval interface.
- `services/control_plane_service.py` centralizes generation, approval, rejection, retry, modification, and status state transitions.
- `services/pagasa_service.py` fetches the authoritative synopsis; `services/forecast_service.py` and `services/forecast_parser.py` provide weather retrieval/parsing responsibilities.
- `plugins/sources/registry.py` provides provider selection. WINDY has implemented intelligent framing; PANaHON has metadata and generic capture but no intelligent map positioning; Meteoblue is placeholder metadata and is not ready to enable.
- `pipelines/weather_pipeline.py` parses forecast text, builds structured forecast/content, captures a provider page, renders a branded graphic, creates deterministic captions, persists an approval job, and sends review.
- `services/caption_template_service.py`, `services/content_composer_service.py`, and their JSON configuration provide the existing deterministic editorial path. This path is working capability and is not to be deprecated because AI is added.
- `helpers/browser.py` performs Playwright screenshot capture. `services/image_rendering_service.py`, `image_service.py`, and map-framing services provide the rendering pipeline.
- Telegram approval supports update, status, approve, text approve, reject, publish retry, modify, image, template, composer, scheduler, language, Windy, and Facebook administration commands.
- The local dashboard and health/control-plane routes exist and must be extended only where bounded additions are needed.
- Facebook publishing and token administration exist through `services/facebook_service.py`, `facebook_admin_service.py`, and the approval workflow.
- Persistence is currently file-based: approval state/history and Facebook token state use repository/runtime filesystem paths; retention handles temporary/manual files. Durable-state design is therefore a real cloud-runtime concern, not an assumed existing database capability.
- VPS support is explicit: ZIP packaging, installer/verification scripts, an example systemd service, and `docs/VPS_DEPLOYMENT.md`. Production secrets are external.
- No `.github/workflows/*` files were present at this baseline. CI economy work must therefore design the first workflow deliberately rather than optimize an existing workflow.
- Current documentation is stronger than the small top-level roadmap: the feature guide records the active flow, interfaces, configurations, and known provider limitations. The implementation roadmap below uses that guide and source evidence as the baseline.

## Architecture boundaries

### Weather truth boundary

Canonical WeatherWatch facts must remain structured, validated, and traceable to the authoritative source. AI input is a controlled projection of those facts plus editorial rules and a small approved-memory subset. AI output may propose wording but may not invent or alter weather systems, locations, warning levels, measurements, storm state, bulletin facts, dates, times, attribution, or unsupported meteorological claims.

### Editorial modes

Both modes are first-class:

- **TEMPLATED**: deterministic rules/configuration produce a headline and caption and remain available when every AI provider is unavailable.
- **AI ASSISTED**: an abstract provider produces structured headline/caption output from controlled WeatherWatch context.

A mode failure must not destroy the other mode. The existing approval workflow remains the convergence point.

### Runtime boundary

A disposable engineering/certification environment may build, test, seed, render, and certify the real subject using disposable state. A persistent VPS or future Render deployment contains only runtime capabilities and persistent state required for operation, observability, security, deployment, rollback, backup/recovery, and maintenance. Production infrastructure is included in engineering certification only when its behavior is itself relevant.

### Source and evidence boundary

Source control remains authoritative. Generated output, approval transitions, publishing results, provider/model metadata, validation results, and deployment verification must be attributable to an identified revision/configuration. Synthetic certification is never production certification.

### Interface preservation boundary

No roadmap lane may remove or make interactive-only any existing CLI/headless, Telegram, dashboard, health, rendering, Facebook, or VPS capability. Any interface change must preserve compatibility or include an explicitly reviewed migration plan.

## Dependency order

```
P0 governance/truth-check
  ↓
P1 editorial domain + TEMPLATED contract
  ↓
P2 AI provider abstraction + output contract
  ↓
P3 fallback + factual validation + provenance
  ↓
P4 curated editorial memory
  ↓
P5 dual-output workflow
  ↓
P6 Telegram/dashboard/CLI surfaces
  ↓
P7 durable state and runtime adapters
  ↓
P8 CI economy
  ↓
P9 integrated synthetic certification
  ↓
P10 deployment verification and Render evaluation
```

Memory may be prototyped after the AI contract, but it must never precede a controlled context schema or bypass factual validation.

## Current Execution Status

This roadmap is actively executing through bounded implementation PRs.

- P0 — COMPLETE: governance and roadmap acceptance.
- P1 — COMPLETE: architecture truth-check and editorial domain boundary.
- P2 — COMPLETE: existing TEMPLATED composer capability verified and preserved.
- P3 — COMPLETE: provider-neutral AI editorial contract.
- P4 — COMPLETE: safe fallback, conservative measurable-claim validation, and provenance.
- P5 — COMPLETE: curated approved-memory boundary and bounded retrieval.
- P6 — COMPLETE: operational mode metadata/status integration across generation, approval state, Telegram status, dashboard health/current-job visibility, and existing headless selection.
- P7 — NEXT: bounded Telegram/dashboard/CLI operational configuration refinements, only where remaining integration is evidenced.
- P8–P12 — NOT STARTED: durable state, Render evaluation, CI economy, integrated certification, and deployment/runtime verification.

Production deployment and production certification have not occurred. TEMPLATED remains the deterministic fallback; AI output is not meteorological authority.

## Roadmap phases

### Phase 0 — Governance and repository alignment

**Why:** Establish the accepted boundary before autonomous workers change a working production-oriented system.

**Dependencies:** None. This is the prerequisite governance and planning gate for all later phases.

**Scope:** Adopt the canonical BKE Engineering Standard, Autonomous Core Instruction, repository-local instructions, this roadmap, and the existing feature guide as the planning authorities. Record the current revision and preserve current interfaces.

**Boundary protected:** Governance and review controls remain the containment boundary; the roadmap itself does not authorize implementation.

**Acceptance:** Every future PR names its bounded requirement, dependencies, preserved interfaces, evidence, and explicit out-of-scope items. No worker treats this roadmap as permission to implement the whole upgrade.

**Verification:** Document inspection, clean branch/base evidence, and independent planning review.

**Risks:** Governance duplication or accidental architecture redesign.

**Out of scope:** Product code, dependency upgrades, provider integration, deployment changes.

### Phase 1 — Architecture truth-check and editorial domain boundary

**Why:** Current flow combines forecast parsing, composition, rendering, approval, and publishing. A stable boundary is needed before AI is introduced.

**Dependencies:** Phase 0. The domain boundary must be based on the accepted governance hierarchy and the inspected current implementation.

**Scope:** Map actual data structures and job fields from ingestion through approval and publication. Define a normalized weather-truth contract and an editorial-output contract without changing behavior. Identify where existing `forecast`, `captions`, `headline`, source attribution, and approval state are persisted.

**Boundary protected:** Raw authoritative facts must not be overwritten by editorial text.

**Acceptance:** A documented contract distinguishes raw source, parsed facts, normalized facts, deterministic editorial output, AI draft, human-modified output, approval state, and publication state. Existing workflow behavior remains unchanged.

**Verification:** Existing parser/composer/approval tests plus focused contract tests. Label evidence as unit/integration, not production certification.

**Risks:** Over-normalizing current data or breaking singleton approval compatibility.

**Out of scope:** AI calls, database migration, dashboard redesign.

### Phase 2 — TEMPLATED composer stabilization

**Why:** TEMPLATED is the deterministic safety path and must remain usable during provider outages.

**Dependencies:** Phase 1. TEMPLATED stabilization depends on the documented weather-truth and editorial-output boundary.

**Scope:** Stabilize the current template/composer path around the normalized facts contract. Preserve config reload, template guardrails, language normalization, post types, headline derivation, Telegram previews, and Facebook publication behavior. Record deterministic fallback behavior.

**Boundary protected:** AI availability must never be required to publish a valid deterministic draft.

**Acceptance:** Given the same approved facts/configuration, TEMPLATED produces deterministic schema-valid headline/caption output. It works with all AI providers disabled.

**Verification:** Existing content-composer, template-guardrail, modify, and publication tests; deterministic repeated-run checks.

**Risks:** Treating current wording as disposable or duplicating composition logic.

**Out of scope:** New editorial memory, provider SDKs, simultaneous dual generation.

### Phase 3 — AI provider/model abstraction and structured output contract

**Why:** AI must be replaceable and configuration-driven rather than coupled to one vendor.

**Dependencies:** Phase 1 and Phase 2. The AI contract must consume the controlled editorial boundary and must not displace the deterministic path.

**Scope:** Define provider/model adapter and router interfaces for OpenRouter, at least two additional configured providers, OpenAI paid fallback, and optional future Ollama/self-hosted support. Define enabled state, priority, model, credential reference, timeout, retry, and fallback policy. Define structured output fields: headline, caption, generation mode, provider, model, validation state.

**Boundary protected:** Provider choice is an operational configuration, not WeatherWatch business logic.

**Acceptance:** A provider can be selected or disabled without changing the editorial domain. Malformed or prose-only responses are rejected. Secrets never enter source control or output metadata.

**Verification:** Adapter contract tests using sandbox/fake peripheral providers; no fake critical WeatherWatch facts or approval boundary.

**Risks:** Provider-specific payload leakage, unbounded retries, quota surprises.

**Out of scope:** Making any provider mandatory; assuming Render can host an LLM; changing TEMPLATED semantics.

### Phase 4 — Provider fallback, factual validation, and provenance

**Why:** A failed provider must degrade safely, and AI wording must not become an unverified weather claim.

**Dependencies:** Phase 3. Fallback, factual validation, and provenance require the provider/model contract and structured output fields.

**Scope:** Ordered fallback for timeout, rate limit, outage, quota, malformed response, invalid structured output, and configured validation failure. Validate AI output against canonical facts as strongly as practical from current parser structures. Record generation mode, provider, model, fallback level, prompt/rules version, memory references, timestamp, validation state, original draft where appropriate, human-edited result, and final approved output without secrets or unnecessary payload retention.

**Boundary protected:** Current validated facts always outrank AI output and memory.

**Acceptance:** AI failure yields explicit AI ASSISTED unavailable/degraded state while TEMPLATED remains available. Invalid output cannot silently enter approval/publication. Provenance identifies what generated and validated the result.

**Verification:** Adversarial tests for invented locations, values, dates, systems, attribution, malformed schema, provider failure, and fallback exhaustion. Preserve exact evidence category.

**Risks:** False confidence from weak validation; leaking prompts or provider data.

**Out of scope:** Calling synthetic output production certification; bypassing human approval.

### Phase 5 — Curated editorial memory and controlled retrieval

**Why:** Approved examples can improve tone and wording without becoming meteorological truth.

**Dependencies:** Phase 3 and Phase 4. Memory requires a controlled AI context schema and must pass through factual-boundary and provenance rules.

**Scope:** Add a curated memory model/source for approved posts, human-written drafts, human corrections, tags by system/location/category/tone, and approval provenance. Retrieve a small relevant subset based on controlled metadata. Define versioning, curation, deletion, and correction behavior.

**Boundary protected:** Memory answers how WeatherWatch writes; it does not answer what weather is occurring.

**Acceptance:** Memory is never injected wholesale by default, never overrides canonical facts, and every selected reference is attributable. Human corrections may improve future context only through an explicit approval/curation path.

**Verification:** Retrieval-size, relevance, isolation, stale-example, and fact-conflict tests.

**Risks:** Prompt growth, stale or biased examples, accidental fact propagation.

**Out of scope:** Autonomous self-training, silent memory mutation, unreviewed corpus ingestion.

### Phase 6 — Dual-output workflow integration

**Why:** Operators need a clear choice between deterministic and AI-assisted editorial output.

**Dependencies:** Phases 2–5. Dual-output review depends on both editorial modes, provider outcomes, validation, memory references, and provenance.

**Scope:** Integrate mode selection with the current control plane and approval state. Where efficient, support AI ASSISTED and TEMPLATED previews with provider/model/status metadata. Preserve select, modify, reject, regenerate where supported, approve, text approval, and publish retry behavior.

**Boundary protected:** Human editorial authority remains final.

**Acceptance:** Operator can choose or configure TEMPLATED, AI ASSISTED, or safe fallback behavior. One mode failing does not destroy the other. Final publication records the selected mode and human modifications.

**Verification:** Control-plane integration tests, Telegram approval tests, dashboard/API tests, and end-to-end synthetic approval flow.

**Risks:** Confusing generated, edited, approved, and published states; accidental auto-publish.

**Out of scope:** Removing Telegram or dashboard; fully autonomous publishing.

### Phase 7 — Telegram, dashboard, and CLI/headless operational surfaces

**Why:** Existing operators already use multiple interfaces; AI must not make one surface the only control path.

**Dependencies:** Phase 6. Operational surfaces should expose the already-defined mode, provider, validation, provenance, and review states without changing existing interfaces.

**Scope:** Add bounded visibility/configuration: AI availability, provider/model, fallback occurrence, mode, validation state, runtime/version, publication/retry status, and safe memory/context summaries. Add provider priority/model/mode management only through existing authorization and config patterns. Add headless flags/configuration for TEMPLATED, AI ASSISTED, and automatic fallback without breaking current commands.

**Boundary protected:** Telegram is a helper/status surface, not the sole interface; local administration and headless automation remain supported.

**Acceptance:** Existing commands and dashboard workflows continue to work. Sensitive credentials and prompt content are not exposed. Headless runs do not require interactive approval unless the existing policy requires it.

**Verification:** Existing Telegram intent, dashboard control-plane, config validation, authorization, and CLI smoke tests.

**Risks:** Interface sprawl, unsafe credential display, configuration drift.

**Out of scope:** Frontend redesign, replacing the dashboard, replacing CLI/headless operation.

### Phase 8 — Durable state and cloud-runtime separation

**Why:** Approval, publication, retry, memory, provenance, and configuration cannot rely indefinitely on a disposable or non-durable local filesystem in a cloud runtime.

**Dependencies:** Phases 1, 6, and 7. Durable-state design must account for existing approval/control-plane behavior and the interfaces that operate it.

**Scope:** Classify current state as ephemeral or durable. Design a repository-compatible persistence adapter and migration strategy for approval state/history, publication state, retries, memory, provenance, provider configuration, and required scheduler state. Keep temporary screenshots/render intermediates disposable. Define backup, restore, retention, concurrency, and corruption recovery.

**Boundary protected:** Persistent state must survive runtime replacement; secrets remain owner-controlled.

**Acceptance:** The plan identifies each state item, custody, retention, recovery method, and compatibility path. No migration is performed by this roadmap commit.

**Verification:** Later implementation must use disposable persistence with real persistence code, migration checks, restart/recovery tests, and a clean-environment restore drill appropriate to risk.

**Risks:** Singleton approval semantics, concurrent Telegram/dashboard actions, token custody, migration loss.

**Out of scope:** Production migration, production secret handling, destructive data conversion.

### Phase 9 — Render as an additional runtime target

**Why:** Render may provide an additional backend/runtime, but the existing VPS is working infrastructure and must remain supported until a justified migration.

**Dependencies:** Phase 8. Runtime evaluation depends on identifying which state is durable and which rendering, scheduler, listener, and persistence capabilities the target must provide.

**Scope:** Evaluate long-running service, scheduler, Telegram listener, browser/rendering dependencies, filesystem semantics, health checks, startup/restart, secrets/configuration, Facebook integration, AI providers, and durable persistence. Isolate runtime adapters from core business logic. Define packaging per target.

**Boundary protected:** Certification environment and persistent runtime are separate; Render is not a universal requirement.

**Acceptance:** A written feasibility decision identifies required services, durable state, browser/runtime constraints, observability, rollback, and deployment verification. VPS remains a supported target unless a separately approved migration exists.

**Verification:** Synthetic runtime certification first; target-specific deployment verification for startup, dependencies, secrets/configuration presence, health, routing where applicable, migrations, critical integration, and rollback.

**Risks:** Browser availability, ephemeral filesystem, long polling, scheduler duplication, provider callback reachability, cost limits.

**Out of scope:** VPS shutdown, production migration, production credential creation, assuming local LLM capability on constrained compute.

### Phase 10 — CI Verification Economy

**Why:** The repository currently has no `.github/workflows` baseline. CI must be designed as a deliberate convergence/certification gate, not an editing loop.

**Dependencies:** Phases 1–9 as applicable. CI tiers must be mapped to real repository commands, deterministic fixtures, runtime boundaries, and certification gates rather than assumed infrastructure.

**Scope:** Define worker-loop commands for syntax, lint/type checks where applicable, focused tests, changed-area tests, and build checks. Add deliberately triggered broader convergence and certification workflows only after repository commands and disposable fixtures are known. Use review-ready, dispatch, protected-branch, release, or equivalent gates rather than unconditional expensive runs on every worker push.

**Boundary protected:** Cost control must not reduce required assurance or fabricate PASS.

**Acceptance:** Tiers are documented; required checks are mapped to phase/risk; failures are observable; remediation reruns invalidated evidence only plus required gates.

**Verification:** Execute worker-loop checks in disposable cloud compute; execute broad certification at meaningful convergence. Label each result PASS/FAIL/PARTIAL/BLOCKED/NOT RUN.

**Risks:** Adding CI before deterministic fixtures exist; duplicate expensive matrices; hidden environment dependence.

**Out of scope:** Making GitHub Actions the only valid CI provider; tying architecture to a provider.

### Phase 11 — Integrated synthetic certification

**Why:** The full editorial path must be proven with real WeatherWatch behavior around a disposable world.

**Dependencies:** Phases 1–10 as applicable. Integrated certification requires the contracts, modes, fallback/validation, state, runtime boundaries, and verification economy to be defined.

**Scope:** Construct synthetic authoritative input fixtures, disposable output/state, sandbox provider adapters, deterministic rendering inputs, fake peripheral Facebook/Telegram boundaries where allowed, and failure scenarios. Real parser, normalization, TEMPLATED/AI contract, validation, approval state machine, rendering boundary, and publication orchestration must execute.

**Boundary protected:** Synthetic certification must execute real WeatherWatch subjects and boundaries without being misrepresented as production certification.

**Acceptance:** Synthetic end-to-end evidence distinguishes facts, generated drafts, human decision, and publication simulation. Test provider outage, malformed AI output, invalid facts, render failure, approval rejection, retry, persistence restart, and rollback/recovery behavior.

**Verification:** Full regression, synthetic end-to-end, security, recovery, and evidence review. Do not call this production certification.

**Risks:** Faking the subject, over-mocking HTTP/state boundaries, retaining secrets in fixtures.

**Out of scope:** Real Facebook publication, real production credentials, production customer data.

### Phase 12 — Deployment/runtime validation and release

**Why:** Engineering certification proves the software; deployment verification proves it was installed and wired correctly in a target environment.

**Dependencies:** Phases 8–11. Deployment validation requires an attributable certified revision/artifact, target runtime decisions, durable-state understanding, and available certification evidence.

**Scope:** For each supported target, deploy an identified certified revision/artifact and perform bounded environment-sensitive verification. Preserve VPS runbook and add target-specific guidance only when needed. Production-specific checks remain where DNS, TLS, external providers, OS installation, network policy, backup topology, or other target behavior is material.

**Boundary protected:** Deployment verification must remain distinct from engineering certification, and production authority, secrets, and destructive actions remain controlled.

**Acceptance:** Source revision/artifact is attributable; runtime starts; dependencies/configuration/secrets are present through approved boundaries; health succeeds; applicable routing/migrations/integration work; rollback remains available. Full engineering certification is not redundantly repeated unless risk requires it.

**Verification:** Deployment verification, smoke checks, rollback/recovery evidence, and production certification where the environment itself is the subject.

**Risks:** Treating synthetic certification as production certification; omitting runtime dependencies; skipping deployment checks.

**Out of scope:** Unauthorized production access, production secret generation, destructive deployment, removal of VPS support.

## Autonomous PR lanes

The following lanes are proposed for future approval and may be split further after Phase 1:

1. Editorial domain contract and TEMPLATED stabilization.
2. Provider/model abstraction and structured AI output contract.
3. Provider fallback, factual validation, and provenance.
4. Curated editorial memory and bounded retrieval.
5. Dual-output control-plane integration.
6. Telegram/dashboard/CLI/headless operational additions.
7. Durable persistence adapter and recovery design.
8. Runtime adapters and Render feasibility/deployment support.
9. CI Verification Economy workflows and evidence reporting.
10. Integrated synthetic certification and release/deployment verification.

Each PR must own a non-overlapping subsystem where practical, state dependencies, preserve existing interfaces, include tests/evidence, and remain independently reviewable. No lane may silently redesign the entire application.

## Verification and evidence policy

Use the canonical status vocabulary:

- **PASS:** executed and verified successfully.
- **FAIL:** executed and produced a failing result; diagnose, fix, and rerun.
- **PARTIAL:** only part of the required behavior executed.
- **BLOCKED:** a genuine unresolved owner/external dependency or authority boundary prevents progress.
- **NOT RUN:** verification has not executed.

PARTIAL and NOT RUN are descriptions, not automatic stop conditions. Missing repository-controlled harnesses, fixtures, configuration, disposable services, migrations, or CI are work to build. Synthetic evidence must state exactly what executed and must not be labeled production certification.

## Explicit non-goals

This roadmap does not:

- implement AI providers, memory, persistence, Render support, or CI;
- remove CLI/headless operation;
- remove Telegram or the local dashboard;
- replace VPS support;
- make Render, Docker, GitHub Actions, OpenAI, OpenRouter, Ollama, or any other technology mandatory;
- permit production secrets, customer data, production signing, or unauthorized provider access in disposable environments;
- authorize autonomous publishing without the existing human authority;
- treat AI output or editorial memory as meteorological truth;
- authorize production migration or destructive data changes.

## Planning completion gate

This roadmap milestone is complete only when the roadmap is committed on its dedicated branch, the branch is pushed, the diff is reviewed for preservation of existing interfaces and safety boundaries, and an independent reviewer can assign the next bounded implementation lane. No product feature implementation is included in this commit.
