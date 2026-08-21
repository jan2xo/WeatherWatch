# WeatherWatch State Boundary

The application uses the `StateRepository` contract in
`storage/state_repository.py`. `WEATHERWATCH_STATE_BACKEND` selects the
backend and defaults to `filesystem`; unknown values fail clearly. The
filesystem backend preserves the existing atomic JSON paths. The additive
`redis` backend stores namespaced JSON documents using
`WEATHERWATCH_REDIS_URL` and is intended for disposable/synthetic verification
and later owner-configured cloud deployment.

This document records the current persistence classification for runtime and
cloud-runtime planning. It does not authorize production migration.

| State | Classification | Current handling |
| --- | --- | --- |
| Approval current job, approval history, publication/retry status, and editorial provenance | DURABLE | `state/approval_state.json`, through `storage.state_repository.JsonStateRepository`; survives process restart and preserves the existing atomic filesystem behavior. |
| AI editorial configuration and other repository-controlled JSON configuration | DURABLE CONFIGURATION | Versioned files under `config/`; provider credentials are not stored there. |
| Curated editorial memory | DURABLE WHEN ENABLED | The current memory boundary is an in-memory interface; a future persisted memory backend must retain approval and factual separation. |
| Scheduler definition | DURABLE CONFIGURATION | `config/scheduler.json`; runtime scheduling itself is reconstructible, while active jobs are not treated as approval state. |
| Facebook access token and token metadata | OWNER-SECRET / EXTERNAL | `state/facebook_token_state.json`; remains outside the generic state abstraction and must use approved secret handling. |

## External backend boundary

The Redis-compatible adapter uses these stable keys:

- `weatherwatch:approval_state`
- `weatherwatch:facebook_token_state`

Missing keys use the domain default factory. Malformed values, connection
failures, and failed writes raise visible errors; they are never converted to
empty state. The adapter does not log URLs, passwords, tokens, or stored
documents.

## Migration and certification status

There is no automatic startup migration and no production migration in this
implementation. An owner migration utility may later read and validate the
filesystem files, write the external keys, verify the result, and retain the
source files; it must support dry-run and must never delete the source
automatically.

Implemented and synthetically verified: filesystem backend, Redis-compatible
adapter, backend selection, namespaced keys, approval/token integration, and
failure-safe behavior. Not yet certified: production Redis configuration,
Render persistent configuration, production migration, backup/restore, and
production recovery verification.
| Render intermediates, screenshots, temporary uploads, and disposable generated assets | EPHEMERAL | Runtime output/data paths and retention rules; safe to recreate or destroy. |

The JSON repository is deliberately a compatibility boundary, not a claim that
the local filesystem is sufficient for every cloud deployment. A future durable
backend may replace it while approval-domain callers retain the same load/save
contract. Production credentials, customer data, and production systems are
out of scope for engineering verification.
