# WeatherWatch

WeatherWatch is a production-oriented Philippine weather editorial and
publishing service. It turns canonical structured weather facts into a branded
WINDY graphic and a templated or AI-assisted draft, then requires human approval
before Facebook publication.

## Current status

Repository-controlled implementation is complete for the pre-runtime candidate.
The Render service has **not** been created or configured, and no live Render,
Redis, WINDY/Chromium, AI, Telegram, Facebook, restart, or production
certification is claimed.

WINDY is the sole operational map provider. PANaHON and Meteoblue are historical,
unregistered modules outside current product scope.

## Canonical flow

```text
PAGASA / canonical structured weather facts
  -> deterministic parsing and framing
  -> WINDY capture
  -> templated or bounded AI editorial generation
  -> factual validation and provenance
  -> rendering
  -> pending approval
  -> authorized Telegram/admin review
  -> explicit approval
  -> Facebook publication
```

AI is an editorial writer, never the weather authority. `templated` remains
usable with no AI credentials, and `automatic` falls back deterministically when
the configured AI chain is unavailable or invalid.

## Runtime topology

WeatherWatch runs as one long-lived Python service containing Telegram polling,
APScheduler, the dashboard and `/health`, Facebook reconnect handling, and the
generation pipeline.

- Canonical build: `bash scripts/build_render.sh`
- Canonical start: `python -m core.service`
- Health path: `/health`
- Managed port: platform `PORT`, bound to `0.0.0.0`
- Local default: `127.0.0.1:8787`
- Python: `.python-version` (`3.13`)

On a public bind, `/admin` and `/admin/current-image` require HTTP Basic with
`ADMIN_DASHBOARD_SECRET`, mutations require the same secret, and `/health`
remains public and secret-free.

The checked-in `render.yaml` is a deterministic deployment definition, not
evidence that deployment occurred. It installs pinned Python dependencies and
Playwright Chromium, provisions a persistent runtime root, and leaves secrets
owner-controlled.

## State and files

`StateRepository` is the only durable-state abstraction:

- local default: filesystem JSON;
- managed runtime: Redis-compatible backend through
  `WEATHERWATCH_STATE_BACKEND=redis` and secret `WEATHERWATCH_REDIS_URL`.

`WEATHERWATCH_RUNTIME_ROOT` relocates mutable configuration, generated output,
uploads, backups, and filesystem state beneath an absolute runtime directory.
On Render, `/var/data/weatherwatch` is backed by the declared disk. Redis keeps
approval and Facebook-token state durable; the disk keeps operator-edited JSON
configuration and regenerable artifacts across deploys. Production backup and
recovery still require live certification.

## Operator commands

Validate the owner-curated editorial corpus without contacting providers:

```bash
python -m tools.editorial_memory schema
python -m tools.editorial_memory validate
python -m tools.editorial_memory validate /path/to/editorial_memory.json
```

All samples must be real owner-approved precedent. Do not populate production
memory with synthetic examples.

## Verification

Hosted convergence executes every `tests/verify_*.py` script, Python
compilation, and secret/scope checks without depending on Render, WINDY,
Telegram, Facebook, Redis cloud, OpenAI, or OpenRouter.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Render runtime runbook](docs/RENDER_RUNTIME.md)
- [Deployment verification boundary](docs/DEPLOYMENT_VERIFICATION.md)
- [AI/editorial operations](docs/AI_EDITORIAL_OPERATIONS.md)
- [Feature and extension guide](docs/FEATURES_AND_EXTENSION_GUIDE.md)
- [Existing VPS deployment](docs/VPS_DEPLOYMENT.md)
