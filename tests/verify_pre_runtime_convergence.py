import base64
import importlib
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "synthetic-test-token",
    "TELEGRAM_CHAT_ID": "1",
    "TELEGRAM_ALLOWED_CHAT_IDS": "1",
    "FACEBOOK_PAGE_ID": "synthetic-page",
}


def configured_environment(**overrides):
    values = dict(REQUIRED_ENV)
    values.update(overrides)
    return patch.dict(os.environ, values, clear=True)


def assert_runtime_validation_contract():
    from config.settings import validate_runtime_config

    with configured_environment():
        validate_runtime_config()

    with configured_environment(TELEGRAM_CHAT_ID="2"):
        try:
            validate_runtime_config()
        except ValueError as error:
            assert "TELEGRAM_CHAT_ID" in str(error)
        else:
            raise AssertionError("outbound Telegram chat escaped allow-list validation")

    with configured_environment(PORT="10000"):
        try:
            validate_runtime_config()
        except ValueError as error:
            assert "ADMIN_DASHBOARD_SECRET" in str(error)
        else:
            raise AssertionError("public dashboard started without authentication")

    with configured_environment(
        PORT="10000",
        ADMIN_DASHBOARD_ENABLED="false",
        ADMIN_DASHBOARD_SECRET="synthetic-admin-secret",
    ):
        try:
            validate_runtime_config()
        except ValueError as error:
            assert "must be true" in str(error)
        else:
            raise AssertionError("managed runtime accepted a disabled HTTP server")

    with configured_environment(FACEBOOK_REDIRECT_URI="https://example.invalid/callback"):
        try:
            validate_runtime_config()
        except ValueError as error:
            assert "configured together" in str(error)
        else:
            raise AssertionError("partial Facebook reconnect configuration was accepted")

    with configured_environment(
        FACEBOOK_APP_ID="synthetic-app",
        FACEBOOK_APP_SECRET="synthetic-secret",
        FACEBOOK_REDIRECT_URI="https://example.invalid/wrong/callback",
    ):
        try:
            validate_runtime_config()
        except ValueError as error:
            assert "/admin/fb/callback" in str(error)
        else:
            raise AssertionError("unsupported Facebook callback route was accepted")


def assert_runtime_root_and_output_contract():
    from config.runtime_paths import runtime_config_path

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        with configured_environment(WEATHERWATCH_RUNTIME_ROOT=str(root)):
            seeded = runtime_config_path("config/scheduler.json")
            assert seeded == root / "config" / "scheduler.json"
            assert seeded.read_text(encoding="utf-8") == Path(
                "config/scheduler.json"
            ).read_text(encoding="utf-8")

            seeded.write_text('{"operator": true}\n', encoding="utf-8")
            assert runtime_config_path("config/scheduler.json").read_text(
                encoding="utf-8"
            ) == '{"operator": true}\n'

            import services.image_rendering_service as rendering_module

            rendering_module = importlib.reload(rendering_module)
            rendering_status = rendering_module.get_image_rendering_status()
            assert Path(rendering_status["config_path"]).is_relative_to(root)
            assert rendering_status["validation_status"] == "valid"

            import core.app as app_module

            app_module = importlib.reload(app_module)
            captured = {}

            def fake_pipeline(job):
                captured.update(job)
                return job

            with patch.object(app_module, "get_current_job", return_value=None), patch.object(
                app_module,
                "get_providers",
                return_value=[{
                    "name": "windy",
                    "display_name": "WINDY",
                    "shorten_url": "windy.com",
                    "url": "https://www.windy.com/example",
                }],
            ), patch.object(app_module, "fetch_daily_forecast", return_value="Forecast"), patch.object(
                app_module, "run_weather_pipeline", side_effect=fake_pipeline
            ):
                app_module.WeatherWatch().update()

            assert Path(captured["raw_output_path"]).is_relative_to(root / "output")
            assert Path(captured["final_output_path"]).is_relative_to(root / "output")


def assert_health_and_dashboard_contract():
    with configured_environment(
        WEATHERWATCH_STATE_BACKEND="redis",
        WEATHERWATCH_REDIS_URL="rediss://user:secret@example.invalid:6380/2",
        PORT="10000",
        ADMIN_DASHBOARD_SECRET="synthetic-admin-secret",
    ):
        import services.admin_dashboard_service as dashboard

        dashboard = importlib.reload(dashboard)
        with patch.object(
            dashboard,
            "get_current_job",
            side_effect=AssertionError("health must not read external state"),
        ), patch.object(
            dashboard,
            "get_facebook_status",
            side_effect=AssertionError("health must not read external token state"),
        ):
            payload = dashboard.build_health_payload()

        assert payload["application_alive"] is True
        assert payload["ok"] is False
        assert payload["status"] == "configured"
        assert payload["durable_state"]["configuration_status"] == "configured"
        assert payload["durable_state"]["live_probe"] == "not_run"
        assert payload["capture_subsystem"]["content_certification"] == "pending"
        assert payload["telegram_status"]["live_probe"] == "not_run"
        assert payload["publication_subsystem"]["live_probe"] == "not_run"
        serialized = str(payload)
        assert "synthetic-admin-secret" not in serialized
        assert "secret@example" not in serialized

        credentials = base64.b64encode(
            b"weatherwatch:synthetic-admin-secret"
        ).decode("ascii")
        assert dashboard.authorize_dashboard_view(None, host="0.0.0.0") is False
        assert dashboard.authorize_dashboard_view(
            f"Basic {credentials}", host="0.0.0.0"
        ) is True
        assert dashboard.authorize_dashboard_view(None, host="127.0.0.1") is True

        from services.facebook_service import create_facebook_oauth_state

        handler = object.__new__(dashboard.AdminDashboardHandler)
        responses = []
        handler.send_html = lambda status, content: responses.append((status, content))
        with patch.object(
            dashboard,
            "reconnect_facebook_with_code",
            return_value={"page_name": "Synthetic Page"},
        ) as reconnect:
            handler.handle_facebook_callback(
                type("Parsed", (), {"query": "state=invalid&code=code"})()
            )
            assert responses[-1][0] == 400
            reconnect.assert_not_called()

            state = create_facebook_oauth_state()
            handler.handle_facebook_callback(
                type("Parsed", (), {"query": f"state={state}&code=code"})()
            )
            assert responses[-1][0] == 200
            reconnect.assert_called_once_with("code")

            handler.handle_facebook_callback(
                type("Parsed", (), {"query": f"state={state}&code=replay"})()
            )
            assert responses[-1][0] == 400
            assert reconnect.call_count == 1


def main():
    assert_runtime_validation_contract()
    assert_health_and_dashboard_contract()
    assert_runtime_root_and_output_contract()
    print("pre-runtime convergence verification ok")


if __name__ == "__main__":
    main()
