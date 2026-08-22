# WeatherWatch Architecture

## Product boundaries

- PAGASA-derived structured facts are meteorological authority.
- AI receives a bounded projection of facts, rules, and approved editorial
  precedent. It cannot replace factual validation.
- WINDY is the only registered operational map provider.
- Human approval is mandatory before Facebook publication.
- `StateRepository` is the sole durable-state abstraction.

## Runtime topology

One Render Docker web service runs one managed Python process:

```text
WeatherWatchService
├── dashboard + /health on PORT
├── authorized Telegram polling
├── APScheduler
├── Facebook reconnect callback
└── update pipeline
    ├── structured weather facts
    ├── WINDY framing and Chromium capture
    ├── templated / AI-assisted editorial path
    ├── factual validation + provenance
    ├── graphic rendering
    └── pending approval persistence
```

The repository-root `Dockerfile` is the canonical managed-runtime artifact and
`python -m core.service` is its canonical start command. Playwright Chromium and
its Linux dependencies are part of the pinned image rather than installed with
privileged package management in a native Render build. The process performs
bounded shutdown of the scheduler and HTTP servers after Telegram polling
returns on Ctrl-C/SIGTERM. Browser page, context, and process lifetimes are
bounded per capture attempt.

## HTTP and health

Local development defaults to `127.0.0.1:8787`. A managed `PORT` binds the
dashboard to `0.0.0.0`; a public dashboard requires
`ADMIN_DASHBOARD_SECRET`. `/health` is cheap, secret-free, and does not call
WINDY, Redis cloud, Telegram, Facebook, or AI providers.

Health distinguishes application liveness from configuration and dependency
readiness. Presence of credentials means configured, not externally certified.

## Capture boundary

The canonical WINDY capture sequence is fixed:

```text
navigation
  -> structural WINDY readiness
  -> 10-second legacy-compatible paint settle
  -> screenshot
  -> artifact integrity validation
```

Capture uses finite retries and closes Playwright resources after success or
failure. Artifact validation proves readable dimensions, not semantically
correct live WINDY content. Center, zoom, pan, and framing remain canonical.

## Editorial boundary

```text
structured facts
  -> editorial context
  -> approved bounded memory
  -> versioned rules
  -> ordered configured AI adapters (optional)
  -> factual validation
  -> provenance
  -> templated fallback when required
```

Provider keys are resolved only from environment references. `provider_2` and
`provider_3` are generic OpenAI-compatible slots whose endpoints and models are
owner-selected; the repository does not invent production models.

## Persistence and filesystem

Approval state and Facebook token state use `StateRepository`, backed by local
JSON or Redis-compatible storage. Redis URLs support AUTH, database selection,
TLS through `rediss://`, bounded socket I/O, and sanitized failure reporting.

`WEATHERWATCH_RUNTIME_ROOT` relocates mutable paths. On the Render blueprint:

- Redis is the durable metadata backend;
- `/var/data/weatherwatch` is the disk-backed runtime root for mutable JSON
  configuration and runtime artifacts;
- screenshots, drafts, uploads, backups, and caches are operational files and
  must not be mistaken for authoritative durable approval state.

## Trust boundaries

- Telegram commands, including `/start` and `/status`, require allowed chat and
  optional user authorization.
- Outbound Telegram delivery must target an allowed chat.
- Public `/admin` and `/admin/current-image` viewing requires HTTP Basic using
  `ADMIN_DASHBOARD_SECRET`; dashboard mutations require the same secret. Local
  loopback viewing remains available. `/health` remains public and secret-free.
- Facebook reconnect uses one-time expiring OAuth state.
- Facebook publication accepts only approved or explicitly retryable jobs.
- Logs, health, and status surfaces omit credentials and raw provider payloads.

## Certification boundary

Repository and hosted synthetic verification may prove the Docker build and
these contracts without external calls. The first native Render attempt proved
that GitHub CI success with `playwright install --with-deps chromium` did not
establish native Render compatibility; that deployment path is retired. Only an
owner-authorized Docker redeployment can prove Render image startup, live
Chromium/WINDY rendering, Redis durability/recovery, AI provider behavior,
Telegram control, Facebook publication, restart/recovery, and production health.
