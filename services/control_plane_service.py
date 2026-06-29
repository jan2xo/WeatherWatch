import threading
from pathlib import Path

from core.app import WeatherWatch
from services.facebook_service import publish_current_job
from services.image_service import run_image_job
from services.post_type_config_service import (
    get_enabled_post_types,
    validate_selected_post_type,
)
from services.windy_layer_service import build_windy_job_metadata
from storage.approval_store import (
    approve_current_job as store_approve_current_job,
    get_current_job,
    reject_current_job as store_reject_current_job,
    update_current_job,
)


APPROVABLE_STATUSES = {"pending", "modified"}
REJECTABLE_STATUSES = {
    "pending",
    "modified",
    "approved",
    "publish_failed",
}
RETRYABLE_STATUSES = {"approved", "publish_failed"}
MODIFIABLE_STATUSES = {"pending", "modified", "publish_failed"}
POST_TYPE_EDITABLE_STATUSES = {"pending", "modified", "publish_failed"}
WINDY_LAYER_EDITABLE_STATUSES = {"pending", "modified", "publish_failed"}

_CONTROL_LOCK = threading.Lock()


def require_current_job(allowed_statuses=None):
    job = get_current_job()
    if not job:
        raise ValueError("No current job.")

    if allowed_statuses and job.get("status") not in allowed_statuses:
        allowed = ", ".join(sorted(allowed_statuses))
        raise ValueError(
            f"Action is not allowed for status {job.get('status')}. "
            f"Allowed statuses: {allowed}."
        )

    return job


def generate_update():
    with _CONTROL_LOCK:
        return WeatherWatch().update()


def approve_current_job(post_type_override=None):
    with _CONTROL_LOCK:
        job = require_current_job(APPROVABLE_STATUSES)

        if post_type_override is not None:
            selected = validate_selected_post_type(post_type_override)
            job = update_current_job({
                "post_type": selected,
                "available_post_types": get_enabled_post_types(),
            })

        approved = store_approve_current_job()
        result = publish_current_job()
        return {
            "job_id": job["job_id"],
            "approved_job": approved,
            **result,
        }


def text_approve_current_job():
    return approve_current_job(post_type_override="text")


def reject_current_job():
    with _CONTROL_LOCK:
        job = require_current_job(REJECTABLE_STATUSES)
        store_reject_current_job()
        return {
            "success": True,
            "job_id": job["job_id"],
            "status": "rejected",
        }


def retry_publish():
    with _CONTROL_LOCK:
        job = require_current_job(RETRYABLE_STATUSES)
        result = publish_current_job()
        return {
            "job_id": job["job_id"],
            **result,
        }


def modify_current_job(headline=None, caption=None):
    with _CONTROL_LOCK:
        job = require_current_job(MODIFIABLE_STATUSES)
        updates = {}

        if headline is not None:
            headline = headline.strip()
            if not headline:
                raise ValueError("Headline cannot be empty.")

            run_image_job({
                "raw_output_path": job["raw_image"],
                "final_output_path": job["image"],
                "headline": headline,
                "source": job["source"],
            })
            updates["headline"] = headline

        if caption is not None:
            caption = caption.strip()
            if not caption:
                raise ValueError("Caption cannot be empty.")

            captions = dict(job.get("captions") or {})
            captions.update({
                "telegram": caption,
                "facebook": caption,
                "instagram": caption,
            })
            updates["caption"] = caption
            updates["captions"] = captions

        if not updates:
            raise ValueError("Provide a headline or caption to modify.")

        updated = update_current_job(updates)
        return {
            "success": True,
            "job": updated,
        }


def set_post_type(post_type):
    with _CONTROL_LOCK:
        job = require_current_job(POST_TYPE_EDITABLE_STATUSES)
        selected = validate_selected_post_type(post_type)

        if selected == "image":
            image_path = job.get("image") or job.get("final_output_path")
            if not image_path or not Path(image_path).is_file():
                raise ValueError(
                    "Image post requires an existing final output image."
                )

        updated = update_current_job(
            {
                "post_type": selected,
                "available_post_types": get_enabled_post_types(),
            },
            preserve_status=job.get("status") == "publish_failed",
        )
        return {
            "success": True,
            "job": updated,
            "post_type": selected,
        }


def set_windy_layer(layer_id):
    with _CONTROL_LOCK:
        job = require_current_job(WINDY_LAYER_EDITABLE_STATUSES)
        if (job.get("provider") or "").lower() != "windy":
            raise ValueError(
                "Windy layer selection is available only for Windy jobs."
            )

        metadata = build_windy_job_metadata(
            framing_decision=job.get("framing_decision"),
            layer_id=layer_id,
        )
        metadata["suggested_windy_layer"] = (
            job.get("suggested_windy_layer")
            or metadata["suggested_windy_layer"]
        )
        updated = update_current_job(
            metadata,
            preserve_status=job.get("status") == "publish_failed",
        )
        return {
            "success": True,
            "job": updated,
            "windy_layer": metadata["windy_layer"],
            "windy_url": metadata["windy_url"],
            "recaptured": False,
        }


def get_current_status():
    job = get_current_job()
    if not job:
        return {
            "has_current_job": False,
            "job": None,
        }

    return {
        "has_current_job": True,
        "job": job,
    }
