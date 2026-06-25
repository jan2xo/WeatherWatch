from services.capture_service import run_capture_job
from services.image_service import run_image_job
from services.telegram_service import run_telegram_job
from services.forecast_service import parse_forecast_text

from services.content_service import (
    build_graphic_headline,
    build_captions,
    build_telegram_review_caption,
)

from storage.approval_store import create_current_job


def run_weather_pipeline(job):
    run_capture_job(job)

    job["forecast"] = parse_forecast_text(
        job.get("forecast_text", "")
    )

    job["content_type"] = job["forecast"]["weather_type"]

    # Generate the GPX/graphic headline BEFORE rendering the image.
    job["headline"] = build_graphic_headline(job)

    run_image_job(job)

    job["captions"] = build_captions(job)

    current_job = create_current_job(job)

    job["caption"] = build_telegram_review_caption(
        job,
        current_job,
    )

    run_telegram_job(job)

    return current_job