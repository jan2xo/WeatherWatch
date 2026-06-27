import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard
import services.control_plane_service as control


def main():
    original_secret = os.environ.get("ADMIN_DASHBOARD_SECRET")
    original_host = os.environ.get("ADMIN_DASHBOARD_HOST")
    secret = "dashboard-test-secret"

    original_dashboard_approve = control.approve_current_job
    original_dashboard_reject = control.reject_current_job
    original_dashboard_modify = control.modify_current_job
    original_dashboard_update = control.generate_update
    original_dashboard_retry = control.retry_publish

    try:
        os.environ["ADMIN_DASHBOARD_SECRET"] = secret
        os.environ["ADMIN_DASHBOARD_HOST"] = "127.0.0.1"

        assert not dashboard.authorize_dashboard_action(
            provided_secret="wrong",
            host="127.0.0.1",
        )
        assert dashboard.authorize_dashboard_action(
            provided_secret=secret,
            host="127.0.0.1",
        )

        calls = []
        control.approve_current_job = lambda: calls.append(
            "approve"
        ) or {"facebook_post_id": "post-1"}
        control.reject_current_job = lambda: calls.append(
            "reject"
        ) or {"job_id": "job-1"}
        control.modify_current_job = (
            lambda headline=None, caption=None: calls.append(
                ("modify", headline, caption)
            ) or {"success": True}
        )
        control.generate_update = lambda: calls.append(
            "update"
        ) or {"success": True}
        control.retry_publish = lambda: calls.append(
            "retry"
        ) or {"facebook_post_id": "post-2"}

        dashboard.dispatch_dashboard_action("/admin/action/update")
        dashboard.dispatch_dashboard_action("/admin/action/approve")
        dashboard.dispatch_dashboard_action("/admin/action/reject")
        dashboard.dispatch_dashboard_action("/admin/action/retry_publish")
        dashboard.dispatch_dashboard_action(
            "/admin/action/modify",
            {"headline": "NEW HEADLINE", "caption": "New caption"},
        )
        assert calls == [
            "update",
            "approve",
            "reject",
            "retry",
            ("modify", "NEW HEADLINE", "New caption"),
        ]

        page = dashboard.render_admin_page().decode("utf-8")
        health = dashboard.build_health_payload()
        assert "/admin/current-image" in page
        assert secret not in page
        assert secret not in str(health)
        assert health["admin_secret_configured"] is True
        assert health["dashboard_actions_enabled"] is True

        original_dashboard_get_job = dashboard.get_current_job
        try:
            dashboard.get_current_job = lambda: {"image": "/etc/passwd"}
            assert dashboard.get_current_image_path() is None

            dashboard.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=dashboard.OUTPUT_ROOT,
                suffix=".png",
            ) as image_file:
                image_file.write(b"test-image")
                image_file.flush()
                dashboard.get_current_job = lambda: {
                    "image": image_file.name,
                }
                assert (
                    dashboard.get_current_image_path()
                    == Path(image_file.name).resolve()
                )
        finally:
            dashboard.get_current_job = original_dashboard_get_job
    finally:
        control.approve_current_job = original_dashboard_approve
        control.reject_current_job = original_dashboard_reject
        control.modify_current_job = original_dashboard_modify
        control.generate_update = original_dashboard_update
        control.retry_publish = original_dashboard_retry

        if original_secret is None:
            os.environ.pop("ADMIN_DASHBOARD_SECRET", None)
        else:
            os.environ["ADMIN_DASHBOARD_SECRET"] = original_secret
        if original_host is None:
            os.environ.pop("ADMIN_DASHBOARD_HOST", None)
        else:
            os.environ["ADMIN_DASHBOARD_HOST"] = original_host

    original_get_job = control.get_current_job
    original_update_job = control.update_current_job
    original_run_image = control.run_image_job
    original_publish = control.publish_current_job

    try:
        current = {
            "job_id": "job-2",
            "status": "pending",
            "headline": "OLD",
            "caption": "Old caption",
            "captions": {"facebook": "Old caption"},
            "raw_image": "raw.png",
            "image": "final.png",
            "source": "Source",
        }
        stored_updates = {}
        control.get_current_job = lambda: current
        control.run_image_job = lambda job: stored_updates.setdefault(
            "image_job",
            job,
        )
        control.update_current_job = lambda updates: {
            **current,
            **updates,
            "status": "modified",
        }

        modified = control.modify_current_job(
            headline="NEW",
            caption="Updated caption",
        )
        assert modified["job"]["headline"] == "NEW"
        assert modified["job"]["captions"]["facebook"] == "Updated caption"
        assert stored_updates["image_job"]["headline"] == "NEW"

        current["status"] = "pending"
        try:
            control.retry_publish()
        except ValueError:
            pass
        else:
            raise AssertionError("Retry should reject pending status")

        current["status"] = "publish_failed"
        control.publish_current_job = lambda: {
            "success": True,
            "facebook_post_id": "post-2",
        }
        assert control.retry_publish()["facebook_post_id"] == "post-2"
    finally:
        control.get_current_job = original_get_job
        control.update_current_job = original_update_job
        control.run_image_job = original_run_image
        control.publish_current_job = original_publish

    print("dashboard control plane verification ok")


if __name__ == "__main__":
    main()
