import copy
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard
import services.control_plane_service as control
import services.windy_layer_service as windy
import storage.approval_store as approval_store
from services.capture_service import resolve_capture_url


def verify_validation():
    config = windy.load_windy_layer_config_file()
    assert windy.validate_windy_layer_config(config)
    assert windy.get_default_layer() == "satellite"

    invalid = copy.deepcopy(config)
    invalid["layers"]["radar"]["url_pattern"] = (
        "https://www.windy.com/?radar,{lat},{lon}"
    )
    try:
        windy.validate_windy_layer_config(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing URL placeholder must fail")

    try:
        windy.get_layer("waves")
    except ValueError:
        pass
    else:
        raise AssertionError("Disabled layer must fail")

    try:
        windy.get_layer("unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown layer must fail")

    original = windy.CONFIG_PATH.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as temporary_dir:
        invalid_upload = Path(temporary_dir) / "invalid.json"
        invalid_upload.write_text(
            json.dumps({"version": "bad"}),
            encoding="utf-8",
        )
        try:
            windy.replace_windy_config_from_file(invalid_upload)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid upload must fail")
    assert windy.CONFIG_PATH.read_text(encoding="utf-8") == original


def verify_urls_and_suggestions():
    assert windy.build_windy_url(
        "satellite", 15.480, 120.600, 5
    ) == (
        "https://www.windy.com/-Satellite-satellite"
        "?satellite,15.480,120.600,5"
    )
    assert windy.build_windy_url(
        "radar", 15.480, 120.600, 5
    ) == (
        "https://www.windy.com/-Weather-radar-radar"
        "?radar,15.480,120.600,5"
    )
    assert windy.build_windy_url(
        "wind", 15.480, 120.600, 5
    ) == "https://www.windy.com/?15.480,120.600,5"

    framing = {
        "center_lat": 15.0,
        "center_lon": 120.0,
        "zoom": 5,
        "pan_x": 0.6,
        "pan_y": 0.48,
    }
    metadata = windy.build_windy_job_metadata(
        framing,
        forecast_data={"affected_weather_system": "Southwest Monsoon"},
    )
    assert metadata["windy_url"].endswith(
        "satellite,15.480,120.600,5"
    )
    assert resolve_capture_url({
        "provider": "windy",
        "url": "legacy",
        **metadata,
    }) == metadata["windy_url"]

    cases = [
        (
            {"affected_weather_system": "Southwest Monsoon"},
            "",
        ),
        ({}, "Low Pressure Area affecting the country"),
        (
            {
                "cyclone_classification": "Typhoon",
                "cyclone_name_local": "TEST",
            },
            "",
        ),
    ]
    assert all(
        windy.suggest_windy_layer(data, text) == "satellite"
        for data, text in cases
    )


def verify_control_plane_and_storage():
    original_get_job = control.get_current_job
    original_update = control.update_current_job
    original_state_file = approval_store.STATE_FILE
    current = {
        "job_id": "windy-job",
        "status": "pending",
        "provider": "windy",
        "suggested_windy_layer": "satellite",
        "framing_decision": {
            "center_lat": 15.48,
            "center_lon": 120.6,
            "zoom": 5,
            "pan_x": 0,
            "pan_y": 0,
        },
    }

    try:
        control.get_current_job = lambda: current
        control.update_current_job = lambda updates, **kwargs: {
            **current,
            **updates,
            "status": (
                current["status"]
                if kwargs.get("preserve_status")
                else "modified"
            ),
        }
        result = control.set_windy_layer("radar")
        assert result["windy_layer"] == "radar"
        assert result["recaptured"] is False
        assert result["job"]["windy_layer_label"] == "Weather Radar"

        current["status"] = "publish_failed"
        failed_result = control.set_windy_layer("wind")
        assert failed_result["job"]["status"] == "publish_failed"

        with tempfile.TemporaryDirectory() as temporary_dir:
            approval_store.STATE_FILE = (
                Path(temporary_dir) / "approval_state.json"
            )
            stored = approval_store.create_current_job({
                **current,
                "windy_layer": "satellite",
                "windy_layer_label": "Satellite",
                "suggested_windy_layer": "satellite",
                "windy_url": windy.build_windy_url(
                    "satellite", 15.48, 120.6, 5
                ),
            })
            assert stored["windy_layer"] == "satellite"
            assert stored["windy_url"].startswith("https://www.windy.com/")
    finally:
        control.get_current_job = original_get_job
        control.update_current_job = original_update
        approval_store.STATE_FILE = original_state_file


def verify_dashboard_security():
    original_secret = os.environ.get("ADMIN_DASHBOARD_SECRET")
    original_set = control.set_windy_layer
    secret = "windy-dashboard-secret"
    calls = []

    try:
        os.environ["ADMIN_DASHBOARD_SECRET"] = secret
        control.set_windy_layer = lambda layer_id: calls.append(
            layer_id
        ) or {
            "windy_layer": layer_id,
            "recaptured": False,
        }
        result = dashboard.dispatch_dashboard_action(
            "/admin/action/windy_layer",
            {"windy_layer": "radar"},
        )
        page = dashboard.render_admin_page().decode("utf-8")
        health = dashboard.build_health_payload()

        assert result["windy_layer"] == "radar"
        assert calls == ["radar"]
        assert "/admin/action/windy_layer" in page
        assert not dashboard.authorize_dashboard_action(
            provided_secret="wrong",
            host="127.0.0.1",
        )
        assert dashboard.authorize_dashboard_action(
            provided_secret=secret,
            host="127.0.0.1",
        )
        assert secret not in page
        assert secret not in str(health)
    finally:
        control.set_windy_layer = original_set
        if original_secret is None:
            os.environ.pop("ADMIN_DASHBOARD_SECRET", None)
        else:
            os.environ["ADMIN_DASHBOARD_SECRET"] = original_secret


def main():
    verify_validation()
    verify_urls_and_suggestions()
    verify_control_plane_and_storage()
    verify_dashboard_security()
    print("Windy layer verification ok")


if __name__ == "__main__":
    main()
