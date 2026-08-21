# WeatherWatch State Boundary

This document records the current persistence classification for runtime and
cloud-runtime planning. It does not authorize production migration.

| State | Classification | Current handling |
| --- | --- | --- |
| Approval current job, approval history, publication/retry status, and editorial provenance | DURABLE | `state/approval_state.json`, through `storage.state_repository.JsonStateRepository`; survives process restart and preserves the existing atomic filesystem behavior. |
| AI editorial configuration and other repository-controlled JSON configuration | DURABLE CONFIGURATION | Versioned files under `config/`; provider credentials are not stored there. |
| Curated editorial memory | DURABLE WHEN ENABLED | The current memory boundary is an in-memory interface; a future persisted memory backend must retain approval and factual separation. |
| Scheduler definition | DURABLE CONFIGURATION | `config/scheduler.json`; runtime scheduling itself is reconstructible, while active jobs are not treated as approval state. |
| Facebook access token and token metadata | OWNER-SECRET / EXTERNAL | `state/facebook_token_state.json`; remains outside the generic state abstraction and must use approved secret handling. |
| Render intermediates, screenshots, temporary uploads, and disposable generated assets | EPHEMERAL | Runtime output/data paths and retention rules; safe to recreate or destroy. |

The JSON repository is deliberately a compatibility boundary, not a claim that
the local filesystem is sufficient for every cloud deployment. A future durable
backend may replace it while approval-domain callers retain the same load/save
contract. Production credentials, customer data, and production systems are
out of scope for engineering verification.

