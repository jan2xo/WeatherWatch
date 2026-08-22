# Deployment Verification Boundary

Repository verification proves the implementation contract. Deployment
verification proves that the same reviewed revision was installed and wired
correctly in a real target. Neither implies the other.

The remaining boundary is owner-controlled: production secrets, infrastructure,
real content, external provider authority, and live evidence stay outside the
repository. Render's ephemeral filesystem must not be treated as durable; use
the declared disk/runtime root and Redis responsibilities described in the
runbook.

## Repository-controlled evidence

Hosted convergence runs every `tests/verify_*.py` verifier with synthetic
credentials and fake external boundaries. It covers:

- managed build/start/port/environment contract;
- browser launch and canonical WINDY capture order;
- filesystem and Redis protocol boundaries;
- health payload and public-dashboard authorization;
- templated and AI editorial contracts, fallback, validation, and provenance;
- editorial-memory schema, CLI validation, and bounded retrieval;
- Telegram/Facebook authorization, redaction, and approval boundary;
- scheduler and clean startup/shutdown lifecycle;
- integrated synthetic certification.

It does not call Render, live WINDY, Redis cloud, Telegram, Facebook, OpenAI, or
OpenRouter.

## Owner-controlled deployment checklist

1. Record the exact reviewed commit deployed by Render.
2. Validate `render.yaml` against Render's current Blueprint schema, then
   confirm `bash scripts/build_render.sh` installs dependencies and Chromium.
3. Confirm `python -m core.service` remains alive and `/health` returns
   `application_alive: true`.
4. Confirm public `/admin` and `/admin/current-image` viewing requires HTTP Basic
   using `ADMIN_DASHBOARD_SECRET`, mutations require the same secret, and
   `/health` remains public and secret-free.
5. Confirm `/var/data/weatherwatch` is the attached disk and runtime root.
6. Confirm Redis uses the intended TLS/AUTH/database, survives restart, and has
   an exercised backup/restore procedure.
7. Capture live WINDY and verify meaningful imagery plus canonical center,
   zoom, pan, readiness, and 10-second paint settle behavior.
8. Validate the real owner-curated editorial corpus with
   `python -m tools.editorial_memory validate`.
9. Configure the owner's actual AI endpoints/models/keys and verify ordered
   fallback, factual rejection, provenance, and deterministic templated fallback.
10. Verify authorized and unauthorized Telegram behavior, polling recovery, and
    `/ai_status` and `/memory_status`.
11. Verify Facebook reconnect, token recovery, approved-only publication, and
    failure/retry state without bypassing human approval.
12. Deliver SIGTERM/restart during representative idle and in-flight states;
    verify scheduler, Telegram, HTTP servers, Redis state, and disk config recover.
13. Exercise rollback to the identified previous revision.
14. Record production smoke and recovery evidence without recording secrets.

## Current truthful status

- Repository implementation: complete candidate, pending exact-head hosted CI.
- Render service creation/configuration: pending.
- Render Chromium/WINDY live certification: pending.
- Production Redis wiring/recovery: pending.
- Actual AI provider/model/key configuration: pending.
- Real editorial memory population: pending.
- Live Telegram verification: pending.
- Live Facebook verification: pending.
- Restart/recovery certification: pending.
- Production certification: pending.

The existing VPS documentation remains available in `docs/VPS_DEPLOYMENT.md`;
this one-shot convergence does not mutate or certify that runtime.
