# Deployment Verification Boundary

Repository verification proves the reviewed Docker artifact and application
contracts. Deployment verification proves that the same revision and image were
installed and wired correctly in the real target. Neither implies the other.

The first real `weatherwatch-dev` deployment is canonical negative evidence. It
used the P21 native Python build and failed at:

```text
python -m playwright install --with-deps chromium
Switching to root user to install dependencies...
Password:
su: Authentication failure
Failed to install browsers
```

Python packages had installed successfully. The failure was specifically the
privileged Linux dependency installation requested by `--with-deps`. GitHub
Actions allowed that operation, so the earlier hosted success did not prove the
native Render contract. The native build path is retired; the repository-root
Dockerfile is the canonical deployment artifact.

The remaining boundary is owner-controlled: production secrets, infrastructure,
real content, external provider authority, and live evidence stay outside the
repository. The container filesystem is ephemeral and must not be treated as
durable; use the declared disk/runtime root and Redis responsibilities described
in the runbook.

## Repository-controlled evidence

Hosted convergence builds the intended pinned Docker image and runs every
`tests/verify_*.py` verifier with synthetic credentials and fake external
boundaries. It covers:

- pinned Playwright package/image compatibility and Chromium presence contract;
- Docker start command, managed port, environment, and health contract;
- absence of privileged browser installation during container startup;
- browser launch and canonical WINDY capture order;
- filesystem and Redis protocol boundaries;
- health payload and public-dashboard authorization;
- templated and AI editorial contracts, fallback, validation, and provenance;
- editorial-memory schema, CLI validation, and bounded retrieval;
- Telegram/Facebook authorization, redaction, and approval boundary;
- scheduler and clean startup/shutdown lifecycle;
- integrated synthetic certification;
- Docker build context protection against `.env`, local runtime output, caches,
  virtual environments, and Git metadata.
- root-owned disk-overlay handoff followed by a non-root WeatherWatch PID 1.

It does not call Render, live WINDY, Redis cloud, Telegram, Facebook, OpenAI, or
OpenRouter. A passing Docker build and synthetic container boot prove the
repository artifact; they do not prove Render container constraints, Chromium
startup, or semantically correct live imagery.

## Owner-controlled Docker deployment checklist

1. Record the exact reviewed commit deployed by Render.
2. Validate `render.yaml` against Render's current Blueprint schema and confirm
   `weatherwatch-dev` uses the Docker runtime with no native `buildCommand`;
   do not create a second service from a mismatched Blueprint name.
   Review the declared paid `starter` plan before applying it; the persistent
   disk contract cannot run on a free Render instance.
3. Confirm Render builds the repository Dockerfile and does not invoke
   `playwright install --with-deps chromium` in a native Python build.
4. Confirm `python -m core.service` remains alive and `/health` returns
   `application_alive: true`.
5. Confirm Chromium launches as the image's documented runtime user without
   adding unreviewed sandbox-disabling flags or elevated capabilities.
6. Confirm public `/admin` and `/admin/current-image` viewing requires HTTP Basic
   using `ADMIN_DASHBOARD_SECRET`, mutations require the same secret, and
   `/health` remains public and secret-free.
7. Confirm `/var/data/weatherwatch` is the attached Render disk and runtime
   root; do not mistake the container filesystem for durable storage.
8. Confirm Redis uses the intended TLS/AUTH/database, survives restart, and has
   an exercised backup/restore procedure.
9. Capture live WINDY and verify meaningful imagery plus canonical center,
   zoom, pan, readiness, and 10-second paint settle behavior.
10. Validate the real owner-curated editorial corpus with
    `python -m tools.editorial_memory validate`.
11. Configure the owner's actual AI endpoints/models/keys and verify ordered
    fallback, factual rejection, provenance, and deterministic templated fallback.
12. Verify authorized and unauthorized Telegram behavior, polling recovery, and
    `/ai_status` and `/memory_status`.
13. Verify Facebook reconnect, token recovery, approved-only publication, and
    failure/retry state without bypassing human approval.
14. Deliver SIGTERM/restart during representative idle and in-flight states;
    verify scheduler, Telegram, HTTP servers, Redis state, and disk config recover.
15. Exercise rollback to the identified previous revision.
16. Record production smoke and recovery evidence without recording secrets.

## Current truthful status

- Native Render Python/Playwright contract: **FAILED and retired**.
- Repository Docker verification: pending the exact-head P22 local/hosted result.
- Existing Render development service Docker redeployment: pending.
- Render Docker process and `/health`: pending.
- Render Chromium launch: pending.
- Live WINDY imagery/framing: pending.
- Production Redis wiring/recovery: pending.
- Actual AI provider/model/key configuration: pending.
- Real editorial memory population: pending.
- Live Telegram verification: pending.
- Live Facebook verification: pending.
- Restart/recovery certification: pending.
- Production certification: pending.

The existing VPS documentation remains available in `docs/VPS_DEPLOYMENT.md`;
this Docker remediation does not mutate or certify that runtime.
