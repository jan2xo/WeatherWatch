import json
import os
import tempfile
import threading
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard
import storage.approval_store as approval_store


def main():
    original = {
        name: os.environ.get(name)
        for name in (
            "PORT",
            "ADMIN_DASHBOARD_HOST",
            "ADMIN_DASHBOARD_PORT",
            "FACEBOOK_PAGE_ID",
            "FACEBOOK_PAGE_ACCESS_TOKEN",
        )
    }
    original_state_file = approval_store.STATE_FILE
    server = None

    try:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "approval_state.json"
            approval_store.STATE_FILE = state_file
            os.environ["PORT"] = "0"
            os.environ.pop("ADMIN_DASHBOARD_HOST", None)
            os.environ.pop("ADMIN_DASHBOARD_PORT", None)
            os.environ["FACEBOOK_PAGE_ID"] = "synthetic-page"
            os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "synthetic-token"

            host, port = dashboard.get_admin_dashboard_address()
            assert host == "0.0.0.0"
            assert port == 0

            server = dashboard.start_admin_dashboard_server()
            actual_port = server.server_address[1]
            response = urllib.request.urlopen(
                f"http://127.0.0.1:{actual_port}/health", timeout=3
            )
            payload = json.loads(response.read().decode("utf-8"))

            assert payload["application_alive"] is True
            assert payload["editorial_subsystem"]["templated_available"] is True
            assert payload["editorial_subsystem"]["ai_optional"] is True
            assert payload["durable_state"]["approval_state_file_present"] is False
            assert "FACEBOOK_PAGE_ACCESS_TOKEN" not in json.dumps(payload)

    finally:
        if server:
            server.shutdown()
            server.server_close()
        approval_store.STATE_FILE = original_state_file
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("runtime compatibility verification ok")


if __name__ == "__main__":
    main()
