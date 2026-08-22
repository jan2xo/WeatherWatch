import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.app as app
import core.scheduler as scheduler
import plugins.sources.registry as registry
from plugins.sources.windy import PROVIDER as WINDY
from services.capture_service import apply_windy_framing
from services.scheduler_config_service import (
    default_scheduler_config,
    validate_scheduler_config,
)


def main():
    assert registry.PROVIDERS == [WINDY]
    assert [provider["name"] for provider in registry.get_providers()] == ["windy"]
    assert not hasattr(registry, "PANAHON")
    assert not hasattr(registry, "METEOBLUE")

    invalid_scheduler = default_scheduler_config()
    invalid_scheduler["jobs"][0]["provider"] = "panahon"
    try:
        validate_scheduler_config(invalid_scheduler)
    except ValueError as error:
        assert "WINDY-only" in str(error)
    else:
        raise AssertionError("Scheduler must reject non-default map providers")

    original_current = app.get_current_job
    original_fetch = app.fetch_daily_forecast
    original_pipeline = app.run_weather_pipeline
    captured = []
    try:
        app.get_current_job = lambda: None
        app.fetch_daily_forecast = lambda: "synthetic PAGASA forecast"
        app.run_weather_pipeline = lambda job: captured.append(job) or {
            "status": "pending"
        }
        result = app.WeatherWatch().update()
        assert result["status"] == "pending"
        assert len(captured) == 1
        assert captured[0]["provider"] == "windy"
        assert captured[0]["provider_display"] == "WINDY"
    finally:
        app.get_current_job = original_current
        app.fetch_daily_forecast = original_fetch
        app.run_weather_pipeline = original_pipeline

    framed_url = apply_windy_framing(
        "https://www.windy.com/-Satellite-satellite?satellite,11.001,125.321,5",
        {
            "enabled": True,
            "center_lat": 13.5,
            "center_lon": 122.5,
            "zoom": 7,
            "pan_x": 1.25,
            "pan_y": -3,
        },
    )
    assert framed_url.endswith("?satellite,10.5000,123.7500,7")

    original_scheduler_current = scheduler.get_current_job
    try:
        scheduler.get_current_job = lambda: None
        calls = []
        result = scheduler.run_weather_update_job(
            {
                "id": "windy-default",
                "provider": "default",
                "skip_if_pending_job_exists": True,
            },
            lambda: calls.append("updated") or "updated",
        )
        assert result == "updated"
        assert calls == ["updated"]
    finally:
        scheduler.get_current_job = original_scheduler_current

    print("WINDY-only provider verification ok")


if __name__ == "__main__":
    main()
