# WeatherWatch state and filesystem boundary

WeatherWatch keeps durable domain state behind the `StateRepository` contract
in `storage/state_repository.py`. `WEATHERWATCH_STATE_BACKEND` selects
`filesystem` (the local-development default) or `redis`. Unknown backends and
invalid Redis configuration fail clearly. Filesystem mode never requires or
contacts Redis.

This boundary prepares the repository for a managed runtime; it does not claim
that a production backend, persistent disk, backup, or recovery procedure has
already been configured or certified.

## Runtime write classification

| Runtime write | Classification | Persistence requirement |
| --- | --- | --- |
| Current approval, approval history, publication/retry status, and editorial provenance | **DURABLE** | Stored through `StateRepository` as `state/approval_state.json` or `weatherwatch:approval_state`. |
| Facebook access token and token metadata | **DURABLE OWNER SECRET** | Stored through the same repository boundary as `state/facebook_token_state.json` or `weatherwatch:facebook_token_state`. Public status projections exclude the access token. |
| Pending raw capture and rendered approval image | **RESTART-SENSITIVE OPERATIONAL ARTIFACT** | The approval record references these files until publication or rejection. A managed runtime must retain them across the supported approval/restart window with `WEATHERWATCH_RUNTIME_ROOT` on owner-configured persistent storage, or explicitly reject/regenerate the pending job before replacement. Redis preserves metadata, not image bytes. |
| Browser screenshots, failed partial captures, completed/rejected output, and processing-only uploads | **EPHEMERAL / REGENERABLE** | May use the managed-service filesystem. Failed partial captures and temporary upload files are removed by their owning workflows. Retention must not delete files referenced by the current approval. |
| Scheduler, AI/editorial, caption, layout, language, and WINDY configuration | **DURABLE CONFIGURATION** | Canonical defaults are versioned under `config/`. Runtime operator edits and backups under `config/` or `data/` will not survive a managed-runtime replacement unless routed through `WEATHERWATCH_RUNTIME_ROOT` and backed by persistent storage, or promoted to canonical source. |
| Curated editorial memory | **DURABLE CONFIGURATION / OWNER CONTENT** | `config/editorial_memory.json` is validated repository/operator content. Real approved examples remain owner-controlled and must not be replaced with synthetic production data. |
| Legacy `output/pending_posts.json` | **LEGACY / NON-CANONICAL** | Used only by legacy `services/approval_bot.py`; it is not the active approval-state boundary and must not be deployed as a second control plane. |

## Runtime root

`config.runtime_paths.runtime_path()` preserves existing repository-relative
paths when `WEATHERWATCH_RUNTIME_ROOT` is unset. When set, writable state,
output, upload, backup, and runtime-mutated configuration paths are rooted under
that directory. The value must be an absolute persistent-disk mount in a
managed runtime. Callers pass only fixed repository-relative paths; absolute or
parent-traversing relative paths are rejected.

Using a runtime root does not make a path durable by itself. Durability comes
from the owner attaching and validating persistent storage at that root.

## Filesystem backend

`JsonStateRepository` creates parent directories as needed and saves by writing,
flushing, and `fsync`-ing a temporary file in the destination directory before
an atomic `os.replace`. A missing file uses the domain default. A corrupt or
transiently unreadable file raises a visible error and is never silently
replaced with empty state.

Filesystem mode is suitable for local development. On a managed service it is
durable only when `WEATHERWATCH_RUNTIME_ROOT` points to persistent storage.

## Redis-compatible backend

Set both:

```text
WEATHERWATCH_STATE_BACKEND=redis
WEATHERWATCH_REDIS_URL=rediss://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

The URL is a secret and must be supplied by the runtime secret store. Supported
semantics are:

- `redis://` for plain TCP and `rediss://` for certificate-verified TLS;
- percent-decoded username/password credentials;
- numeric database selection from the URL path (default database `0`);
- a three-second bounded connect/read/write/authentication timeout;
- one connection per operation, always closed in `finally`;
- raw sockets closed if TLS setup fails;
- stable keys `weatherwatch:approval_state` and
  `weatherwatch:facebook_token_state`.

Query strings, fragments, nonnumeric database paths, invalid ports, and a
username without a password are rejected. Missing keys use the domain default
factory. Malformed JSON, connection failures, authentication failures, and
failed writes raise safe public errors and never become empty state. Error
messages and health payloads do not include the Redis URL, credentials, stored
document, or raw server error reply.

## Health and failure semantics

Health checks validate backend selection and URL shape without connecting to
Redis. Therefore:

- filesystem reports `ready` because its local repository boundary is usable;
- a syntactically valid Redis configuration reports `configured`, not `ready`;
- missing or invalid Redis configuration reports `degraded`;
- live Redis reachability is proven only by an actual bounded state operation
  or a separate owner-controlled runtime certification.

If Redis is selected but unavailable, state access fails visibly. WeatherWatch
does not silently fall back to filesystem, because that would split durable
approval/token state across backends. Local filesystem mode remains independent
and does not need Redis.

## Migration, backup, and certification

No automatic filesystem-to-Redis migration is performed. An owner-controlled
migration must validate source state, write the stable keys, read them back,
retain the source files, and support a dry run. It must never delete source
state automatically.

Repository verification covers atomic filesystem behavior, Redis URL/TLS/AUTH/
database semantics, bounded timeouts, connection cleanup, safe errors,
namespaced approval/token integration, runtime-root path safety, and offline
health reporting. Still owner/runtime-controlled: production Redis wiring,
persistent-disk attachment, backup/restore, restart recovery, and production
certification.
