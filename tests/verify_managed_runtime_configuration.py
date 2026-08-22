from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def assert_blueprint_contract():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")

    required_lines = (
        'version: "1"',
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
        "maxShutdownDelaySeconds: 30",
        "disk:",
        "name: weatherwatch-runtime",
        "mountPath: /var/data/weatherwatch",
        "sizeGB: 1",
        "key: ADMIN_DASHBOARD_SECRET",
        "generateValue: true",
        "key: WEATHERWATCH_STATE_BACKEND",
        "value: redis",
        "key: WEATHERWATCH_RUNTIME_ROOT",
        "value: /var/data/weatherwatch",
        "key: WEATHERWATCH_REDIS_URL",
        "key: TELEGRAM_BOT_TOKEN",
        "key: TELEGRAM_CHAT_ID",
        "key: TELEGRAM_ALLOWED_CHAT_IDS",
        "key: FACEBOOK_PAGE_ID",
        "key: FACEBOOK_PAGE_ACCESS_TOKEN",
        "key: FACEBOOK_GRAPH_API_VERSION",
        "value: v26.0",
        "sync: false",
    )
    for line in required_lines:
        assert line in blueprint, f"render.yaml is missing: {line}"

    forbidden_values = (
        "synthetic-test-token",
        "synthetic-page",
        "OPENROUTER_API_KEY=",
        "OPENAI_API_KEY=",
        "FACEBOOK_PAGE_ACCESS_TOKEN=",
        "TELEGRAM_BOT_TOKEN=",
    )
    assert not any(value in blueprint for value in forbidden_values)

    env_entries = {}
    current_key = None
    for raw_line in blueprint.splitlines():
        line = raw_line.strip()
        if line.startswith("- key: "):
            current_key = line.removeprefix("- key: ")
            env_entries[current_key] = {}
        elif current_key and ": " in line:
            field, value = line.split(": ", 1)
            env_entries[current_key][field] = value.strip('"')

    assert env_entries["ADMIN_DASHBOARD_SECRET"] == {"generateValue": "true"}
    assert env_entries["WEATHERWATCH_STATE_BACKEND"] == {"value": "redis"}
    assert env_entries["WEATHERWATCH_RUNTIME_ROOT"] == {
        "value": "/var/data/weatherwatch"
    }
    assert env_entries["FACEBOOK_GRAPH_API_VERSION"] == {"value": "v26.0"}
    for secret_name in (
        "WEATHERWATCH_REDIS_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "FACEBOOK_PAGE_ID",
        "FACEBOOK_PAGE_ACCESS_TOKEN",
    ):
        assert env_entries[secret_name] == {"sync": "false"}


def assert_python_and_build_contract():
    python_version = (PROJECT_ROOT / ".python-version").read_text(
        encoding="utf-8"
    ).strip()
    assert python_version == "3.12"

    build_script = (PROJECT_ROOT / "scripts/build_render.sh").read_text(
        encoding="utf-8"
    )
    assert "set -eu" in build_script
    assert "python -m pip install" in build_script
    assert "-r requirements.txt" in build_script
    assert "python -m pip check" in build_script
    assert "python -m playwright install" not in build_script
    assert "--with-deps" not in build_script
    assert "python -m compileall -q" in build_script

    requirements = (PROJECT_ROOT / "requirements.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    required_packages = {
        "apscheduler",
        "pillow",
        "playwright",
        "python-dotenv",
        "python-telegram-bot",
        "requests",
    }
    pinned = {
        line.split("==", 1)[0].strip().lower()
        for line in requirements
        if "==" in line
    }
    assert required_packages <= pinned

    workflow = (PROJECT_ROOT / ".github/workflows/convergence.yml").read_text(
        encoding="utf-8"
    )
    assert "docker build --tag weatherwatch-ci:verify ." in workflow
    assert "Verify Chromium in the deployment artifact" in workflow
    assert "Smoke test managed startup, health, and shutdown" in workflow
    assert "tests/verify_*.py" in workflow


def assert_managed_port_contract():
    dashboard_source = (
        PROJECT_ROOT / "services/admin_dashboard_service.py"
    ).read_text(encoding="utf-8")
    assert 'if not host and get_optional_env("PORT"):' in dashboard_source
    assert 'host = "0.0.0.0"' in dashboard_source
    assert 'or get_optional_env("PORT")' in dashboard_source
    assert "or DEFAULT_DASHBOARD_PORT" in dashboard_source


def assert_safe_environment_contract():
    settings_source = (PROJECT_ROOT / "config/settings.py").read_text(
        encoding="utf-8"
    )
    for required in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "FACEBOOK_PAGE_ID",
    ):
        assert required in settings_source
    assert (
        "TELEGRAM_CHAT_ID must be listed in TELEGRAM_ALLOWED_CHAT_IDS"
        in settings_source
    )
    assert (
        "ADMIN_DASHBOARD_SECRET is required for a public dashboard"
        in settings_source
    )
    assert (
        "ADMIN_DASHBOARD_ENABLED must be true when PORT is configured"
        in settings_source
    )
    assert (
        "WEATHERWATCH_REDIS_URL is required for the redis state backend"
        in settings_source
    )
    assert "must be configured together" in settings_source

    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for placeholder in (
        "TELEGRAM_BOT_TOKEN=",
        "FACEBOOK_PAGE_ACCESS_TOKEN=",
        "WEATHERWATCH_REDIS_URL=",
        "OPENROUTER_API_KEY=",
        "OPENAI_API_KEY=",
    ):
        assert placeholder in example
    assert "synthetic-test-token" not in example
    assert "rediss://" not in example


def main():
    assert_blueprint_contract()
    assert_python_and_build_contract()
    assert_managed_port_contract()
    assert_safe_environment_contract()
    print("managed runtime configuration verification ok")


if __name__ == "__main__":
    main()
