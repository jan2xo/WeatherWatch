from core.approval_store import create_current_job
from workers.capture_worker import run_capture_job
from workers.image_worker import run_image_job
from workers.telegram_worker import run_telegram_job


def run_weather_pipeline(job):
    run_capture_job(job)
    run_image_job(job)

    job["caption"] = (
        "📡 NORTH LUZON WEATHER WATCH\n\n"
        "General weather update ready for review.\n\n"
        f"{job['source']}"
    )

    create_current_job(job)
    run_telegram_job(job)

    return job