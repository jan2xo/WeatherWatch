# CI Verification Economy

WeatherWatch separates cheap worker-loop feedback from deliberate remote
convergence and certification. GitHub Actions is not the autonomous worker's
editing loop.

## Tier 1 — worker loop

Disposable development compute runs compile checks, focused tests, changed-area
tests, targeted integration tests, and relevant builds while a bounded task is
being implemented. Workers may repeat these checks without consuming remote CI
minutes.

## Tier 2 — convergence

`.github/workflows/convergence.yml` is the minimum remote convergence gate. It
runs only when a pull request is marked ready for review, or when deliberately
started with `workflow_dispatch`. It is path-filtered, uses one Python version,
and runs one deterministic/runtime suite without a matrix or duplicate jobs.

The workflow uses synthetic environment values only. It does not call Telegram,
Facebook, AI providers, Render, the VPS, or production systems.

## Tier 3 — certification

Full synthetic end-to-end, security, recovery, release, and deployment
verification remain explicit later gates. They are not silently implied by a
green convergence workflow. Production certification and deployment checks must
use their own authorization and evidence boundary.

## Trigger and cost policy

There is no push trigger. A worker can iterate locally, then the orchestrator
marks a converged PR ready for review to obtain one remote result. Manual
dispatch is available for a deliberate rerun. Concurrency prevents accidental
parallel duplicate runs for the same PR while preserving an in-flight result.

## Evidence vocabulary

PASS means the listed checks actually executed successfully. A skipped or
unavailable workflow is NOT RUN or BLOCKED as applicable; it must not be
reported as certification PASS.

