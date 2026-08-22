import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard


def main():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_url = os.environ.get("WEATHERWATCH_REDIS_URL")
    original_page_id = os.environ.get("FACEBOOK_PAGE_ID")
    original_page_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")
    original_current_job = dashboard.get_current_job
    original_facebook_status = dashboard.safe_facebook_status
    try:
        dashboard.get_current_job = lambda: None
        dashboard.safe_facebook_status = lambda: {"status": "configured"}
        os.environ["FACEBOOK_PAGE_ID"] = "synthetic-page"
        os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "synthetic-token"
        os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        health = dashboard.build_health_payload()
        durable = health["durable_state"]
        assert durable["state_backend"] == "filesystem"
        assert durable["state_backend_status"] == "ready"
        assert durable["available"] is True

        os.environ["WEATHERWATCH_STATE_BACKEND"] = "redis"
        os.environ["WEATHERWATCH_REDIS_URL"] = f"redis://:{'super' + 'secret'}@localhost:6379/2"
        health = dashboard.build_health_payload()
        durable = health["durable_state"]
        assert durable["state_backend_status"] == "configured"
        assert durable["available"] is False
        assert "supersecret" not in str(health)
        assert "redis://" not in str(health)

        os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        health = dashboard.build_health_payload()
        durable = health["durable_state"]
        assert durable["state_backend_status"] == "degraded"
        assert durable["available"] is False
        assert "WEATHERWATCH_REDIS_URL" in durable["state_backend_error"]
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_url is None:
            os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        else:
            os.environ["WEATHERWATCH_REDIS_URL"] = original_url
        if original_page_id is None:
            os.environ.pop("FACEBOOK_PAGE_ID", None)
        else:
            os.environ["FACEBOOK_PAGE_ID"] = original_page_id
        if original_page_token is None:
            os.environ.pop("FACEBOOK_PAGE_ACCESS_TOKEN", None)
        else:
            os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = original_page_token
        dashboard.get_current_job = original_current_job
        dashboard.safe_facebook_status = original_facebook_status
    print("state backend health verification ok")


if __name__ == "__main__":
    main()
