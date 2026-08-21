import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.app as app
import core.scheduler as scheduler
from plugins.sources.registry import resolve_providers
from services.scheduler_config_service import (
    default_scheduler_config,
    validate_scheduler_config,
)


def expect_failure(callback, expected):
    try:
        callback()
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError(f"Expected failure containing: {expected}")


def main():
    config = default_scheduler_config()
    assert validate_scheduler_config(config)
    assert [item["name"] for item in resolve_providers("default")] == ["windy"]
    assert [item["name"] for item in resolve_providers("windy")] == ["windy"]
    expect_failure(lambda: resolve_providers("unknown"), "Unknown")
    expect_failure(lambda: resolve_providers("panahon"), "disabled")

    unknown = copy.deepcopy(config)
    unknown["jobs"][0]["provider"] = "unknown"
    expect_failure(lambda: validate_scheduler_config(unknown), "unknown")
    disabled = copy.deepcopy(config)
    disabled["jobs"][0]["provider"] = "panahon"
    expect_failure(lambda: validate_scheduler_config(disabled), "disabled")

    events = []
    default_job = {"id": "default", "provider": "default"}
    assert scheduler.run_weather_update_job(
        default_job,
        lambda: events.append(("default", None)) or "ok",
    ) == "ok"
    explicit_job = {"id": "wind", "provider": "windy"}
    assert scheduler.run_weather_update_job(
        explicit_job,
        lambda **kwargs: events.append(("windy", kwargs["requested_provider"])) or "ok",
    ) == "ok"
    assert events == [("default", None), ("windy", "windy")]

    original_current = scheduler.get_current_job
    original_reject = scheduler.reject_current_job
    try:
        scheduler.get_current_job = lambda: {"job_id": "old", "status": "pending"}
        scheduler.reject_current_job = lambda: events.append(("rejected", None))
        result = scheduler.run_weather_update_job(
            {"id": "wind", "provider": "windy"},
            lambda **kwargs: events.append(("updated", kwargs["requested_provider"])),
            {"auto_reject_before_next_run": True},
        )
        assert result is None
        assert events[-2:] == [("rejected", None), ("updated", "windy")]

        scheduler.get_current_job = lambda: {"job_id": "approved", "status": "approved"}
        result = scheduler.run_weather_update_job(
            {"id": "wind", "provider": "windy"},
            lambda **kwargs: events.append(("should-not-run", kwargs)),
        )
        assert result["skipped"] is True
    finally:
        scheduler.get_current_job = original_current
        scheduler.reject_current_job = original_reject

    original_resolve = app.resolve_providers
    original_current = app.get_current_job
    original_fetch = app.fetch_daily_forecast
    original_pipeline = app.run_weather_pipeline
    try:
        captured = []
        app.get_current_job = lambda: None
        app.fetch_daily_forecast = lambda: "synthetic forecast"
        app.run_weather_pipeline = lambda job: captured.append(job) or {"status": "pending"}
        app.resolve_providers = lambda requested: [{
            "name": requested or "windy",
            "display_name": "WINDY",
            "shorten_url": "windy.com",
            "url": "https://www.windy.com/",
        }]
        result = app.WeatherWatch().update(requested_provider="windy")
        assert result["status"] == "pending"
        assert captured[0]["provider"] == "windy"

        attempts = []
        app.resolve_providers = lambda requested: [
            {
                "name": "first",
                "display_name": "FIRST",
                "shorten_url": "first.example",
                "url": "https://first.example/",
            },
            {
                "name": "second",
                "display_name": "SECOND",
                "shorten_url": "second.example",
                "url": "https://second.example/",
            },
        ]

        def default_pipeline(job):
            attempts.append(job["provider"])
            if job["provider"] == "first":
                raise RuntimeError("first provider unavailable")
            return {"status": "pending"}

        app.run_weather_pipeline = default_pipeline
        result = app.WeatherWatch().update()
        assert result["status"] == "pending"
        assert attempts == ["first", "second"]

        app.resolve_providers = lambda requested: (_ for _ in ()).throw(
            ValueError("explicit provider failed")
        )
        try:
            app.WeatherWatch().update(requested_provider="windy")
        except ValueError as error:
            assert "explicit provider failed" in str(error)
        else:
            raise AssertionError("Explicit provider failure must propagate")
    finally:
        app.resolve_providers = original_resolve
        app.get_current_job = original_current
        app.fetch_daily_forecast = original_fetch
        app.run_weather_pipeline = original_pipeline

    print("scheduler provider selection verification ok")


if __name__ == "__main__":
    main()
