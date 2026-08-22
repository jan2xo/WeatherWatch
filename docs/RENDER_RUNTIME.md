# Render Runtime Runbook

This is the canonical repository-controlled Render contract. It does not
authorize deployment and is not evidence that any Render resource exists.

## Service topology

Use one Render Python web service. Do not add a separate worker or process
manager:

- build command: `bash scripts/build_render.sh`
- start command: `python -m core.service`
- health path: `/health`
- Python version: `.python-version` (`3.13`)
- shutdown allowance: 30 seconds
- automatic deployment: disabled until the owner authorizes it

The process contains the dashboard/health server, Telegram polling, scheduler,
Facebook reconnect callback, and update pipeline. Render supplies `PORT`; the
application binds `0.0.0.0:<PORT>`. Local defaults remain
`127.0.0.1:8787`.

## Build and Chromium

`scripts/build_render.sh` performs:

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m playwright install --with-deps chromium
python -m compileall -q main.py config core helpers pipelines plugins services storage
```

Chromium is not assumed to exist. Live WINDY capture still requires target
certification after deployment. The repository preserves the proven sequence:

```text
navigation -> structural readiness -> 10-second paint settle
           -> screenshot -> artifact validation
```

## Disk and state topology

The blueprint declares a 1 GB disk mounted at `/var/data/weatherwatch` and sets:

```text
WEATHERWATCH_RUNTIME_ROOT=/var/data/weatherwatch
WEATHERWATCH_STATE_BACKEND=redis
WEATHERWATCH_REDIS_URL=<owner secret>
```

The responsibilities are different:

- Redis-compatible state stores approval/history and Facebook token state
  (secret token plus public metadata) through the existing `StateRepository`
  abstraction. Treat the Redis service and its backups as secret-bearing.
- The disk retains operator-edited runtime JSON configuration, uploads, backups,
  and regenerable artifacts rooted beneath `WEATHERWATCH_RUNTIME_ROOT`.
- Screenshots and rendered drafts are regenerable. Their presence must never be
  treated as proof that approval/publication metadata is durable.

A Render persistent disk is runtime-only: it is not mounted during build or
pre-deploy commands. A disk-backed service is limited to one instance, cannot
use horizontal scaling, and does not receive zero-downtime deploys. This matches
WeatherWatch's single-process approval architecture; the owner must account for
the restart window during deployment certification.

Use a managed `rediss://` URL when TLS is required. The adapter supports AUTH,
optional username, database selection, bounded socket timeouts, and sanitized
errors. `/health` reports Redis as configured without opening a live connection.
Connection, backup, restore, and recovery must be certified against the actual
owner-selected Redis service.

## Environment contract

Never put values in Git or `render.yaml`. `sync: false` means the owner supplies
the value during service creation.

Required to start:

| Variable | Kind | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | secret | Telegram polling/delivery |
| `TELEGRAM_CHAT_ID` | non-secret ID | outbound approval chat |
| `TELEGRAM_ALLOWED_CHAT_IDS` | non-secret IDs | inbound authorization; must include outbound chat |
| `FACEBOOK_PAGE_ID` | non-secret ID | configured publication Page |
| `ADMIN_DASHBOARD_SECRET` | secret | required because `PORT` makes the dashboard public |
| `WEATHERWATCH_REDIS_URL` | secret | required by blueprint Redis mode |

Optional or feature-specific:

- `TELEGRAM_ALLOWED_USER_IDS`: further restrict users inside allowed chats.
- `FACEBOOK_PAGE_ACCESS_TOKEN`: Facebook publishing fallback.
- `FACEBOOK_GRAPH_API_VERSION`: non-secret version selector; the repository
  default is `v26.0` and must be revalidated during live Facebook certification.
- `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI`: configure
  all three together for OAuth reconnect. Use exactly the deployed HTTPS URL
  ending in `/admin/fb/callback`.
- `WEATHERWATCH_EDITORIAL_MODE`: `templated`, `ai_assisted`, or `automatic`.
- AI provider enabled/model/timeout variables plus their key and endpoint
  variables documented in `.env.example` and `docs/AI_EDITORIAL_OPERATIONS.md`.

The repository blueprint starts in `templated` mode. Do not enable providers or
choose models until the owner supplies an approved endpoint/model/key set.

## First start

1. Create/configure the service from the reviewed exact revision.
2. Attach the declared disk and owner-selected Redis-compatible service.
3. Enter required secrets/IDs; confirm the outbound Telegram chat is allowlisted.
4. Keep AI in `templated` until provider configuration is intentionally tested.
5. Start the service with no customer or production publication data.
6. Check `/health`; treat `application_alive` as liveness and component fields as
   configuration/readiness evidence, not live-provider certification.
   Redis mode reports top-level `configured`/`ok: false` until real availability
   is established outside the cheap health request.
7. Verify public `/admin` and `/admin/current-image` viewing requires HTTP Basic
   with the dashboard secret and every mutation requires the same secret.
   `/health` must remain public and secret-free.
8. Perform the bounded live checks in `docs/DEPLOYMENT_VERIFICATION.md`.

## Restart behavior

SIGTERM/Ctrl-C lets Telegram polling return, stops APScheduler, then closes the
Facebook and dashboard HTTP servers with bounded waits. Per-attempt browser
resources are already closed by the capture boundary. After restart:

- approval and Facebook token state reload through Redis;
- mutable JSON configuration reloads from the disk-backed runtime root;
- temporary capture/render work may be regenerated;
- a failed publication remains explicit and retryable only through the existing
  approval boundary.

This lifecycle is synthetically verified. Render restart, disk remount, Redis
recovery, and in-flight job behavior remain live certification debt.

## Certification checklist

- `render.yaml` validates against Render's current Blueprint schema;
- exact deployed revision recorded;
- build completes and Chromium exists;
- process starts and `/health` responds;
- public dashboard viewing and mutation authorization enforced while `/health`
  remains public/secret-free;
- disk path is mounted and writable;
- Redis TLS/AUTH/database and restart recovery verified;
- live WINDY capture produces meaningful imagery with canonical framing;
- real editorial corpus validates;
- configured AI order/fallback verified without changing weather facts;
- authorized Telegram commands and shutdown verified;
- approved-only Facebook publication and reconnect verified;
- restart, rollback, backup, and recovery evidence recorded.

Until these execute on the actual target, Render implementation and production
certification remain pending.
