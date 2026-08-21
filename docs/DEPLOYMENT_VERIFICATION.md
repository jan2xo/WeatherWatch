# Deployment Verification Boundary

This document separates repository-controlled engineering evidence from
owner-controlled deployment evidence. No deployment is implied by this file.

## Engineering certification already available

The disposable synthetic suite verifies the real parser, deterministic
composition, editorial contract and fallback, factual validation, provenance,
memory selection, approval/retry state, restart reload, dashboard health, and
managed-runtime port behavior. It uses synthetic provider and credential values
and does not mutate external services.

## Deployment verification checklist

After an authorized deployment to a selected runtime, verify only the
environment-sensitive boundary first:

1. The deployed revision or immutable artifact matches the identified reviewed
   source revision.
2. The service starts and remains alive under the runtime supervisor.
3. `/health` is reachable and reports `application_alive: true`.
4. Required durable state is attached to an approved persistent backend; no
   ephemeral filesystem is treated as durable by assumption.
5. Required environment configuration and secrets are present without being
   printed or committed.
6. Telegram polling/control and dashboard access work when enabled.
7. Facebook publishing remains behind the existing human approval boundary.
8. The rollback/recovery path remains available.

Full engineering certification does not need to be repeated on the deployment
target when the same certified source/artifact is deployed. Deployment
verification answers whether that certified artifact was correctly installed
and wired in this environment.

## Owner-controlled boundary

Real deployment requires the owner to choose and authorize the runtime account,
service, billing/plan where applicable, durable storage, and production secrets
such as Telegram/Facebook credentials. Domain/DNS, provider participation, and
production publication authority are also external boundaries.

The smallest next owner action is: provide an approved deployment target and
secret boundary for a non-production or production environment, if deployment
verification is desired. Until then, P12 remains BLOCKED at deployment
authorization, not at engineering implementation.

## Existing VPS

The existing VPS/systemd path remains the supported deployment path and is
covered by `docs/VPS_DEPLOYMENT.md` and `scripts/verify_install.sh`. Nothing in
the managed-runtime evaluation replaces it.

