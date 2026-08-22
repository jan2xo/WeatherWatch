from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT_VERSION = "1.60.0"
PLAYWRIGHT_IMAGE = (
    "mcr.microsoft.com/playwright/python:v1.60.0-noble@sha256:"
    "abf13b369f8829eb45e29df38d6c5221f7e7521649cb5d2de7989c82bdb574ad"
)


def assert_dockerfile_contract():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    first_from = next(
        line.strip() for line in dockerfile.splitlines() if line.startswith("FROM ")
    )
    assert first_from == f"FROM {PLAYWRIGHT_IMAGE}"
    assert ":latest" not in dockerfile
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "HOME=/home/pwuser" in dockerfile
    assert "sys.version_info[:2] == (3, 12)" in dockerfile
    assert 'USER root' in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/weatherwatch-entrypoint"]' in dockerfile
    assert 'CMD ["python", "-m", "core.service"]' in dockerfile
    assert "playwright install" not in dockerfile
    assert "apt-get" not in dockerfile
    assert "requirements.txt pins playwright==1.60.0" in dockerfile

    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"^playwright==([^\s]+)$", requirements, re.MULTILINE)
    assert match and match.group(1) == PLAYWRIGHT_VERSION


def assert_render_blueprint_contract():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    for required in (
        "- type: web",
        "name: weatherwatch-dev",
        "runtime: docker",
        "region: singapore",
        "plan: starter",
        "dockerfilePath: ./Dockerfile",
        "dockerContext: .",
        "dockerCommand: python -m core.service",
        "healthCheckPath: /health",
        'autoDeployTrigger: "off"',
        "mountPath: /var/data/weatherwatch",
        "key: WEATHERWATCH_RUNTIME_ROOT",
        "value: /var/data/weatherwatch",
    ):
        assert required in blueprint, f"render.yaml is missing: {required}"

    for obsolete in (
        "runtime: python",
        "buildCommand:",
        "startCommand:",
        "scripts/build_render.sh",
    ):
        assert obsolete not in blueprint, f"obsolete Render contract remains: {obsolete}"


def assert_build_context_and_helper_contract():
    ignored = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    required_ignores = {
        ".git",
        ".github",
        ".venv",
        "**/__pycache__",
        "**/*.py[cod]",
        ".env",
        ".env.*",
        "output",
        "state",
        "logs",
        "data/*_backups",
        "data/*_uploads",
    }
    assert required_ignores <= set(ignored)

    helper = (PROJECT_ROOT / "scripts/build_render.sh").read_text(encoding="utf-8")
    assert "local/CI Python dependency verification only" in helper
    assert "playwright install" not in helper
    assert "--with-deps" not in helper

    entrypoint = (PROJECT_ROOT / "scripts/docker_entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "runtime_disk=/var/data/weatherwatch" in entrypoint
    assert 'chown -R pwuser:pwuser "${runtime_disk}"' in entrypoint
    assert "setpriv --reuid=pwuser --regid=pwuser --init-groups" in entrypoint
    assert "WEATHERWATCH_RUNTIME_ROOT" not in entrypoint


def main():
    assert_dockerfile_contract()
    assert_render_blueprint_contract()
    assert_build_context_and_helper_contract()
    print("Render Docker runtime verification ok")


if __name__ == "__main__":
    main()
