import threading

from core.app import WeatherWatch
from services.facebook_service import publish_current_job
from services.image_service import run_image_job
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


def approve_current_job():
    with _CONTROL_LOCK:
        job = require_current_job(APPROVABLE_STATUSES)
        approved = store_approve_current_job()
        result = publish_current_job()
        return {
            "job_id": job["job_id"],
            "approved_job": approved,
            **result,
        }


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
