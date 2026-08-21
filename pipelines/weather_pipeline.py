from services.capture_service import run_capture_job
from services.image_service import run_image_job
from services.telegram_service import run_telegram_job
from services.forecast_service import parse_forecast_text
from services.map_framing_service import determine_map_framing
from services.windy_layer_service import build_windy_job_metadata

from services.content_service import (
    build_graphic_headline,
    build_captions,
    build_telegram_review_caption,
)

from storage.approval_store import create_current_job
from services.editorial_generation_service import generate_ai_editorial


def run_weather_pipeline(job):
    job["forecast"] = parse_forecast_text(
        job.get("forecast_text", ""),
        provider_metadata={
            "provider": job.get("provider"),
            "provider_display": job.get("provider_display"),
            "provider_url": job.get("provider_url"),
        },
    )

    job["content_type"] = job["forecast"]["weather_type"]

    if job.get("requested_editorial_mode") != "templated":
        try:
            draft, provenance = generate_ai_editorial(job["forecast"]["structured"])
            job["editorial_mode"] = "ai_assisted"
            job["ai_status"] = "available"
            job["ai_provider"] = provenance["provider"]
            job["ai_model"] = provenance["model"]
            job["ai_fallback_level"] = provenance["fallback_level"]
            job["ai_validation_state"] = provenance["validation_state"]
            job["editorial_provenance"] = provenance
            job["_ai_headline"] = draft.headline
            job["_ai_caption"] = draft.caption
        except Exception as error:
            job["editorial_mode"] = "templated"
            job["ai_status"] = "fallback/degraded"
            job["ai_validation_state"] = "not_run"
            job["editorial_provenance"] = {
                "mode": "templated",
                "status": "fallback/degraded",
                "error": str(error),
            }
    job["framing_decision"] = determine_map_framing(
        forecast_data=job["forecast"]["structured"],
        parsed_forecast_text=job["forecast"]["raw_text"],
    )

    if (job.get("provider") or "").lower() == "windy":
        job.update(build_windy_job_metadata(
            framing_decision=job["framing_decision"],
            forecast_data=job["forecast"]["structured"],
            parsed_forecast_text=job["forecast"]["raw_text"],
            layer_id=job.get("windy_layer"),
        ))
        job["url"] = job["windy_url"]

    run_capture_job(job)

    # Generate the GPX/graphic headline BEFORE rendering the image.
    job["headline"] = build_graphic_headline(job)
    if job.get("_ai_headline"):
        job["headline"] = job["_ai_headline"]

    run_image_job(job)

    job["captions"] = build_captions(job)
    if job.get("_ai_caption"):
        job["captions"] = {
            **job["captions"],
            "facebook": job["_ai_caption"],
            "telegram": job["_ai_caption"],
            "instagram": job["_ai_caption"],
        }

    current_job = create_current_job(job)

    job["caption"] = build_telegram_review_caption(
        job,
        current_job,
    )

    run_telegram_job(job)

    return current_job
