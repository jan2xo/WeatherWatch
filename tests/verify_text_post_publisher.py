import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard
import services.control_plane_service as control
import services.facebook_service as facebook
import services.post_type_config_service as post_types


def verify_config():
    config = post_types.default_post_type_config()
    assert config["default_post_type"] == "image"
    assert post_types.validate_post_type_config(config)

    disabled = post_types.default_post_type_config()
    disabled["facebook"]["text"]["enabled"] = False
    try:
        post_types.validate_selected_post_type("text", disabled)
    except ValueError:
        pass
    else:
        raise AssertionError("Disabled post type must be rejected")

    try:
        post_types.validate_selected_post_type("audio", config)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported post type must be rejected")

    with tempfile.TemporaryDirectory() as temporary_dir:
        invalid_path = Path(temporary_dir) / "post_types.json"
        invalid_path.write_text(
            json.dumps({"default_post_type": "text"}),
            encoding="utf-8",
        )
        try:
            post_types.load_post_type_config_file(invalid_path)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid config must not load")


def verify_control_plane():
    original_get_job = control.get_current_job
    original_update = control.update_current_job

    with tempfile.NamedTemporaryFile(suffix=".jpg") as image_file:
        current = {
            "job_id": "job-1",
            "status": "pending",
            "image": image_file.name,
            "post_type": "image",
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

            changed = control.set_post_type("text")
            assert changed["post_type"] == "text"
            assert changed["job"]["post_type"] == "text"

            changed = control.set_post_type("image")
            assert changed["post_type"] == "image"

            current["image"] = None
            assert control.set_post_type("text")["post_type"] == "text"
            try:
                control.set_post_type("image")
            except ValueError:
                pass
            else:
                raise AssertionError("Image mode must require final output")

            current["status"] = "publishing"
            try:
                control.set_post_type("text")
            except ValueError:
                pass
            else:
                raise AssertionError(
                    "Publishing jobs must reject mode changes"
                )
        finally:
            control.get_current_job = original_get_job
            control.update_current_job = original_update


def verify_publish_dispatch():
    original_photo = facebook.publish_photo_post
    original_text = facebook.publish_text_post
    calls = []

    try:
        facebook.publish_photo_post = (
            lambda image_path, caption: calls.append(
                ("image", image_path, caption)
            ) or {"post_id": "image-post"}
        )
        facebook.publish_text_post = (
            lambda message: calls.append(("text", message))
            or {"id": "text-post"}
        )

        text_result = facebook.publish_job({
            "post_type": "text",
            "captions": {"facebook": "Text-only weather update"},
        })
        image_result = facebook.publish_job({
            "post_type": "image",
            "image": "output/final.jpg",
            "captions": {"facebook": "Image weather update"},
        })

        assert text_result["id"] == "text-post"
        assert image_result["post_id"] == "image-post"
        assert calls == [
            ("text", "Text-only weather update"),
            ("image", "output/final.jpg", "Image weather update"),
        ]
    finally:
        facebook.publish_photo_post = original_photo
        facebook.publish_text_post = original_text


def verify_retry_preserves_post_type():
    original_get_job = facebook.get_current_job
    original_mark_publishing = facebook.mark_current_publishing
    original_mark_posted = facebook.mark_current_posted
    original_mark_failed = facebook.mark_current_publish_failed
    original_publish_job = facebook.publish_job
    seen = []

    try:
        facebook.get_current_job = lambda: {
            "job_id": "job-2",
            "status": "publish_failed",
            "post_type": "text",
            "captions": {"facebook": "Retry me"},
        }
        facebook.mark_current_publishing = lambda: None
        facebook.mark_current_posted = lambda facebook_post_id=None: None
        facebook.mark_current_publish_failed = lambda error: None
        facebook.publish_job = lambda job: seen.append(
            job["post_type"]
        ) or {"id": "retry-post"}

        result = facebook.publish_current_job()
        assert result["facebook_post_id"] == "retry-post"
        assert seen == ["text"]
    finally:
        facebook.get_current_job = original_get_job
        facebook.mark_current_publishing = original_mark_publishing
        facebook.mark_current_posted = original_mark_posted
        facebook.mark_current_publish_failed = original_mark_failed
        facebook.publish_job = original_publish_job


def verify_intent_based_approval():
    original_get_job = control.get_current_job
    original_update = control.update_current_job
    original_store_approve = control.store_approve_current_job
    original_publish = control.publish_current_job
    events = []
    current = {
        "job_id": "job-approve",
        "status": "pending",
        "post_type": "image",
    }

    try:
        control.get_current_job = lambda: current

        def update_job(updates):
            current.update(updates)
            current["status"] = "modified"
            events.append(("updated", current["post_type"]))
            return dict(current)

        def store_approve():
            current["status"] = "approved"
            events.append(("approved", current["post_type"]))
            return dict(current)

        control.update_current_job = update_job
        control.store_approve_current_job = store_approve
        control.publish_current_job = lambda: events.append(
            ("published", current["post_type"])
        ) or {
            "success": True,
            "facebook_post_id": "text-approve-post",
        }

        result = control.text_approve_current_job()
        assert result["facebook_post_id"] == "text-approve-post"
        assert events == [
            ("updated", "text"),
            ("approved", "text"),
            ("published", "text"),
        ]

        events.clear()
        current.update({"status": "pending", "post_type": "image"})
        control.approve_current_job()
        assert events == [
            ("approved", "image"),
            ("published", "image"),
        ]
    finally:
        control.get_current_job = original_get_job
        control.update_current_job = original_update
        control.store_approve_current_job = original_store_approve
        control.publish_current_job = original_publish


def verify_dashboard():
    original_set_post_type = control.set_post_type
    original_text_approve = control.text_approve_current_job
    original_secret = os.environ.get("ADMIN_DASHBOARD_SECRET")
    secret = "native-text-test-secret"
    calls = []

    try:
        os.environ["ADMIN_DASHBOARD_SECRET"] = secret
        control.set_post_type = lambda value: calls.append(value) or {
            "post_type": value,
        }
        control.text_approve_current_job = lambda: calls.append(
            "text_approve"
        ) or {
            "post_type": "text",
            "facebook_post_id": "text-post",
        }
        result = dashboard.dispatch_dashboard_action(
            "/admin/action/post_type",
            {"post_type": "text"},
        )
        text_result = dashboard.dispatch_dashboard_action(
            "/admin/action/text_approve"
        )
        page = dashboard.render_admin_page().decode("utf-8")
        health = dashboard.build_health_payload()

        assert result["post_type"] == "text"
        assert text_result["post_type"] == "text"
        assert calls == ["text", "text_approve"]
        assert 'action="/admin/action/post_type"' in page
        assert 'action="/admin/action/text_approve"' in page
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
        control.set_post_type = original_set_post_type
        control.text_approve_current_job = original_text_approve
        if original_secret is None:
            os.environ.pop("ADMIN_DASHBOARD_SECRET", None)
        else:
            os.environ["ADMIN_DASHBOARD_SECRET"] = original_secret


def main():
    verify_config()
    verify_control_plane()
    verify_publish_dispatch()
    verify_retry_preserves_post_type()
    verify_intent_based_approval()
    verify_dashboard()
    print("native text post publisher verification ok")


if __name__ == "__main__":
    main()
