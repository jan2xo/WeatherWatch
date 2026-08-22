# Render Runtime Evaluation

This is an engineering compatibility record, not a deployment authorization.
Render is an additional runtime target; the existing VPS/systemd deployment
remains supported.

## Evidence-backed topology

WeatherWatch currently uses one long-lived Python process:

```text
core.service
├── Telegram polling
├── APScheduler
├── local admin dashboard and /health
├── optional Facebook reconnect server
└── WeatherWatch update pipeline
```

The existing VPS service starts `python -m core.service` and systemd provides
restart supervision. No separate queue worker or web-only process is currently
required by the repository. A managed-runtime deployment should therefore use
the same application entrypoint unless a later scaling requirement proves that
the topology must split.

## Managed-runtime adapter

The dashboard keeps its existing local defaults (`127.0.0.1:8787`). When an
explicit `ADMIN_DASHBOARD_HOST` or `ADMIN_DASHBOARD_PORT` is supplied, those
values win. Otherwise, a generic `PORT` environment variable selects
`0.0.0.0:<PORT>`, which permits a managed runtime health check without adding a
provider-specific branch to application logic.

Suggested repository-controlled service settings are:

```text
Build command: python -m pip install -r requirements.txt
Start command: python -m core.service
Health path: /health
```

These are configuration instructions, not a claim that a service has been
created or deployed.

## Required external configuration

The following values remain external runtime configuration. No values belong in
source control:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ALLOWED_CHAT_IDS`
- `FACEBOOK_PAGE_ID`
- `FACEBOOK_PAGE_ACCESS_TOKEN` when Facebook publishing is enabled
- `FACEBOOK_REDIRECT_URI` when reconnect is enabled
- `ADMIN_DASHBOARD_SECRET` when the dashboard is not loopback-only
- `WEATHERWATCH_EDITORIAL_MODE` and the repository-controlled AI config

Provider credentials, tokens, customer data, and production URLs are not part
of synthetic verification.

## Filesystem and durability boundary

Render services have an ephemeral filesystem unless an explicitly supported
persistent disk or external durable backend is attached. Therefore:

- `storage/approval_state.json` is durable application state and must not be
  assumed to survive managed-runtime replacement without a durable storage
  decision;
- `config/` files are deployment configuration and should be supplied through
  the built artifact or an approved configuration process;
- render intermediates, screenshots, temporary uploads, and generated assets
  are ephemeral;
- Facebook token state remains owner-secret/external and is not moved into
  synthetic or generic state storage.

P8's `JsonStateRepository` is the compatibility boundary. P9 does not claim a
cloud database migration or production persistence. A future deployment must
choose and verify a durable backend before relying on runtime replacement.

## Health semantics

`/health` remains secret-free and now distinguishes application liveness,
durable-state availability, editorial readiness, AI optional/degraded state,
and publication configuration. Optional AI failure does not make the
TEMPLATED path unavailable. The existing `ok` field remains conservative for
operational dependency readiness; `application_alive` is the liveness signal.

## Synthetic verification boundary

The P9 runtime check binds the dashboard to an ephemeral local port, exercises
`/health`, confirms the TEMPLATED configuration remains valid when AI is not
available, and verifies the state path is isolated. It does not call Telegram,
Facebook, AI providers, Render, the VPS, or any production system.

PR #15 adds an optional Redis-compatible state backend selected by
`WEATHERWATCH_STATE_BACKEND=redis` and `WEATHERWATCH_REDIS_URL`. Filesystem
JSON remains the default and VPS-compatible mode. Synthetic tests cover the
adapter and failure boundaries; production Redis configuration, Render
persistent wiring, migration, backup/restore, and recovery remain deployment
verification work and were not performed here.
