import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from storage.approval_store import get_current_job, mark_current_posted


load_dotenv()


def get_facebook_config():
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    page_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    if not page_id:
        raise ValueError("Missing FACEBOOK_PAGE_ID in .env")

    if not page_access_token:
        raise ValueError("Missing FACEBOOK_PAGE_ACCESS_TOKEN in .env")

    return page_id, page_access_token


def publish_photo_post(image_path: str, caption: str):
    page_id, page_access_token = get_facebook_config()

    image_file = Path(image_path)

    if not image_file.exists():
        raise FileNotFoundError(f"Facebook image not found: {image_file}")

    url = f"https://graph.facebook.com/v20.0/{page_id}/photos"

    with image_file.open("rb") as photo:
        response = requests.post(
            url,
            data={
                "caption": caption,
                "access_token": page_access_token,
                "published": "true",
            },
            files={
                "source": photo,
            },
            timeout=60,
        )

    if not response.ok:
        raise RuntimeError(f"Facebook publish failed: {response.text}")

    return response.json()


def publish_current_job():
    job = get_current_job()

    if not job:
        raise ValueError("No current job to publish.")

    if job.get("status") != "approved":
        raise ValueError(f"Current job is not approved. Status: {job.get('status')}")

    result = publish_photo_post(
        image_path=job["image"],
        caption=job["caption"],
    )

    facebook_post_id = result.get("post_id") or result.get("id")
    mark_current_posted(facebook_post_id=facebook_post_id)

    return {
        "success": True,
        "facebook_result": result,
        "facebook_post_id": facebook_post_id,
    }