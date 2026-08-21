import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import core.app as app
import services.admin_dashboard_service as dashboard
import services.control_plane_service as control


def verify_generated_job_records_mode_boundary():
    original_current = app.get_current_job
    original_providers = app.get_providers
    original_fetch = app.fetch_daily_forecast
    original_pipeline = app.run_weather_pipeline
    captured = {}

    try:
        app.get_current_job = lambda: None
        app.get_providers = lambda: [{
            "name": "test",
            "display_name": "TEST",
            "shorten_url": "test.example",
            "url": "https://test.example",
        }]
        app.fetch_daily_forecast = lambda: "PAGASA forecast"

        def fake_pipeline(job):
            captured.update(job)
            return {"job_id": "job-1", "status": "pending"}

        app.run_weather_pipeline = fake_pipeline
        result = app.WeatherWatch().update("automatic")

        assert result["status"] == "pending"
        assert captured["requested_editorial_mode"] == "automatic"
        assert captured["editorial_mode"] == "templated"
        assert captured["ai_status"] == "unavailable/degraded"
        assert captured["ai_validation_state"] == "not_run"
    finally:
        app.get_current_job = original_current
        app.get_providers = original_providers
        app.fetch_daily_forecast = original_fetch
        app.run_weather_pipeline = original_pipeline


def verify_explicit_ai_does_not_fallback_silently():
    original_current = app.get_current_job
    try:
        app.get_current_job = lambda: None
        try:
            app.WeatherWatch().update("ai_assisted")
        except RuntimeError as error:
            assert "TEMPLATED remains available" in str(error)
        else:
            raise AssertionError("Explicit unavailable AI must remain visible")
    finally:
        app.get_current_job = original_current


def verify_dashboard_and_control_plane_visibility():
    job = {
        "job_id": "job-1",
        "status": "pending",
        "provider": "TEST",
        "requested_editorial_mode": "automatic",
        "editorial_mode": "templated",
        "ai_status": "unavailable/degraded",
        "ai_provider": None,
        "ai_model": None,
        "ai_fallback_level": None,
        "ai_validation_state": "not_run",
        "editorial_provenance": {"mode": "templated"},
    }
    original_control_job = control.get_current_job
    original_dashboard_job = dashboard.get_current_job
    original_facebook_id = os.environ.get("FACEBOOK_PAGE_ID")
    original_facebook_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")
    try:
        control.get_current_job = lambda: job
        dashboard.get_current_job = lambda: job
        os.environ["FACEBOOK_PAGE_ID"] = "123"
        os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "test"

        editorial = control.get_editorial_status()
        summary = dashboard.current_job_summary()
        health = dashboard.build_health_payload()

        assert editorial["editorial_mode"] == "templated"
        assert summary["ai_status"] == "unavailable/degraded"
        assert health["requested_editorial_mode"] == "automatic"
        assert health["editorial_provenance"] == {"mode": "templated"}
    finally:
        control.get_current_job = original_control_job
        dashboard.get_current_job = original_dashboard_job
        if original_facebook_id is None:
            os.environ.pop("FACEBOOK_PAGE_ID", None)
        else:
            os.environ["FACEBOOK_PAGE_ID"] = original_facebook_id
        if original_facebook_token is None:
            os.environ.pop("FACEBOOK_PAGE_ACCESS_TOKEN", None)
        else:
            os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = original_facebook_token


if __name__ == "__main__":
    verify_generated_job_records_mode_boundary()
    verify_explicit_ai_does_not_fallback_silently()
    verify_dashboard_and_control_plane_visibility()
    print("editorial operational integration verification ok")
