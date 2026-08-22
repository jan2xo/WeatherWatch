# Render Docker Runtime Runbook

This is the canonical repository-controlled Render contract. It does not
authorize deployment, mutate the existing `weatherwatch-dev` service, or prove
that a Docker image has run on Render.

## Why the runtime is Docker-based

The first real Render development deployment used the former P21 native Python
contract:

```text
build: bash scripts/build_render.sh
start: python -m core.service
```

The build installed Python dependencies, then failed at:

```text
python -m playwright install --with-deps chromium
Switching to root user to install dependencies...
Password:
su: Authentication failure
Failed to install browsers
```

`--with-deps` installs Linux packages as well as browser binaries. GitHub
Actions permitted that privileged package installation; Render's native Python
build environment did not. The passing GitHub job therefore proved the script
only in its own runner, not in Render. Native Render installation of Chromium
system dependencies is no longer part of the WeatherWatch deployment contract.

## Service topology

Use one Render Docker web service. Do not add a separate worker, browser
sidecar, or process manager:

- Blueprint service name: `weatherwatch-dev`, matching the existing development
  target rather than creating a parallel service;
- instance plan: `starter`, because Render persistent disks require paid
  compute; applying the Blueprint can therefore upgrade an existing free
  development service and the owner must review the resulting cost first;
- build artifact: repository-root `Dockerfile`;
- base: Microsoft Playwright Python `v1.60.0-noble`, pinned by digest;
- Python: 3.12, matching the image and `.python-version`;
- runtime user: the image's unprivileged `pwuser`;
- start command: `python -m core.service`;
- health path: `/health`;
- shutdown allowance: 30 seconds;
- automatic deployment: disabled until the owner authorizes it.

The process contains the dashboard/health server, Telegram polling, scheduler,
Facebook reconnect callback, and update pipeline. Render supplies `PORT`; the
application binds `0.0.0.0:<PORT>`. Local defaults remain
`127.0.0.1:8787`.

## Docker, Playwright, and Chromium

The Dockerfile pins `mcr.microsoft.com/playwright/python:v1.60.0-noble` by
immutable digest. Its Playwright release matches `playwright==1.60.0` in
`requirements.txt`. The image supplies Chromium browser binaries, Linux shared
libraries, and fonts; the Python Playwright package is installed separately
from the repository's pinned requirements. Matching these versions is required:
a mismatched Playwright client may not locate the image's browser executable.

System dependency installation is already represented by the immutable base
image. The container entrypoint starts with only enough privilege to repair
ownership of the fixed `/var/data/weatherwatch` mount (which can mask image-time
ownership), then replaces PID 1 with WeatherWatch as `pwuser`. It never derives
the privileged target from an environment variable. The running application
does not perform `apt`, `su`, `playwright install --with-deps`, or other package
installation. `HOME` is explicitly `/home/pwuser`, keeping browser/Python caches
out of `/root`; the application writes only to the paths described below.

The Docker image makes Chromium available; it does not certify that Chromium
can launch under Render's live container constraints or that WINDY imagery
paints correctly. The capture sequence remains unchanged:

```text
navigation -> structural readiness -> 10-second paint settle
           -> screenshot -> artifact validation
```

Do not add `--no-sandbox`, privileged containers, or broad Linux capabilities
without a separately reviewed need supported by live evidence.

## Build and start

Render builds the repository Dockerfile and starts its declared `CMD`. There is
no native Render `buildCommand`, and Render must not call
`scripts/build_render.sh`. That script is retained only as a host engineering
dependency/compile verifier; it does not install browsers or Linux packages.

For repository engineering, build the same artifact:

```bash
docker build --tag weatherwatch:p22 .
```

The hosted convergence workflow performs a bounded container health/shutdown
smoke test with synthetic configuration, a root-owned Docker volume at the
canonical disk path, an explicit non-root PID 1 assertion, and no external
network access. Do not pass production credentials as Docker build arguments or
bake `.env` files into layers. `.dockerignore` excludes local environments,
credentials, runtime artifacts, caches, editor files, and Git metadata from the
build context.

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

The container filesystem is ephemeral. A `VOLUME` declaration or a path inside
the image would not create Render durability; only the attached Render disk
backs `/var/data/weatherwatch`. A Render persistent disk is runtime-only: it is
not mounted during image build or pre-deploy commands. A disk-backed service is
limited to one instance, cannot use horizontal scaling, and does not receive
zero-downtime deploys. This matches WeatherWatch's single-process approval
architecture; the owner must account for the restart window during deployment
certification. Render disks are available only on paid compute, so the checked-in
Blueprint explicitly selects `starter`; this is a repository contract, not an
authorization to apply billing changes before owner review.

Use a managed `rediss://` URL when TLS is required. The adapter supports AUTH,
optional username, database selection, bounded socket timeouts, and sanitized
errors. `/health` reports Redis as configured without opening a live connection.
Connection, backup, restore, and recovery must be certified against the actual
owner-selected Redis service.

## Environment contract

Never put secret values in Git, the Dockerfile, image build arguments, image
layers, or `render.yaml`. `sync: false` means the owner supplies the value during
service creation or configuration.

Required to start the managed configuration:

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

## First Docker redeployment

1. Review and merge the exact Docker-remediation revision; record its SHA.
2. Apply the reviewed `render.yaml` Docker service contract to the existing
   development workspace without copying the obsolete native build command.
3. Confirm the declared disk and owner-selected Redis-compatible service.
4. Enter required secrets/IDs; confirm the outbound Telegram chat is allowlisted.
5. Keep AI in `templated` until provider configuration is intentionally tested.
6. Deploy with no customer or production publication data.
7. Check `/health`; treat `application_alive` as liveness and component fields as
   configuration/readiness evidence, not live-provider certification. Redis mode
   reports top-level `configured`/`ok: false` until real availability is
   established outside the cheap health request.
8. Verify public `/admin` and `/admin/current-image` viewing requires HTTP Basic
   with the dashboard secret and every mutation requires the same secret.
   `/health` must remain public and secret-free.
9. Perform the bounded live checks in `docs/DEPLOYMENT_VERIFICATION.md`.

## Restart behavior

SIGTERM/Ctrl-C lets Telegram polling return, stops APScheduler, then closes the
Facebook and dashboard HTTP servers with bounded waits. Per-attempt browser
resources are already closed by the capture boundary. After restart:

- approval and Facebook token state reload through Redis;
- mutable JSON configuration reloads from the disk-backed runtime root;
- temporary capture/render work may be regenerated;
- a failed publication remains explicit and retryable only through the existing
  approval boundary.

This lifecycle is synthetically verified. Render Docker shutdown, disk remount,
Redis recovery, and in-flight job behavior remain live certification debt.

## Certification status and checklist

The evidence categories must remain separate:

- Repository Docker verification: established only by an exact-head Docker
  build/smoke test and hosted convergence result recorded on the PR.
- Render Docker deployment: **PENDING** until the existing service successfully
  builds and starts the reviewed image.
- Live Render Chromium launch: **PENDING**.
- Live WINDY imagery and framing: **PENDING**.

Live certification must record:

- exact deployed revision and image build result;
- process startup and `/health` response;
- dashboard authorization and public secret-free health;
- disk mount and write behavior;
- Redis TLS/AUTH/database and restart recovery;
- Chromium availability under the deployed runtime user;
- meaningful live WINDY imagery with canonical framing and paint settle;
- real editorial corpus validation;
- configured AI order/fallback without changing weather facts;
- authorized Telegram behavior and shutdown;
- approved-only Facebook publication and reconnect;
- restart, rollback, backup, and recovery evidence.

Until these execute on the actual target, Render Docker implementation and
production certification remain pending.
