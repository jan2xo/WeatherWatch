from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from services.scheduler_config_service import get_scheduler_config
from storage.approval_store import get_current_job, reject_current_job


scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Manila"))
_update_callback = None


def run_weather_update_job(
    job_config,
    update_callback,
    pending_job_policy=None,
):
    current_job = get_current_job()
    policy = pending_job_policy or {}

    if current_job and policy.get("auto_reject_before_next_run"):
        reject_statuses = policy.get(
            "reject_statuses",
            ["pending", "modified"],
        )
        if current_job.get("status") in reject_statuses:
            reject_current_job()
            print(
                "Scheduled job auto-rejected stale approval: "
                f"{current_job.get('job_id')} "
                f"({current_job.get('status')})"
            )
            current_job = None

    if job_config.get("skip_if_pending_job_exists", True):
        if current_job:
            print(
                "Scheduled job skipped: "
                f"{job_config['id']} - current job "
                f"{current_job.get('job_id')} is "
                f"{current_job.get('status')}"
            )
            return {
                "skipped": True,
                "reason": "current_job_exists",
            }

    return update_callback()


def register_scheduler_jobs(config, update_callback, scheduler_instance=None):
    target_scheduler = scheduler_instance or scheduler
    target_scheduler.remove_all_jobs()

    if not config.get("enabled"):
        print("Scheduler disabled by config.")
        return []

    timezone = ZoneInfo(config["timezone"])
    registered = []

    for job_config in config["jobs"]:
        if not job_config.get("enabled"):
            continue

        hour, minute = (int(part) for part in job_config["time"].split(":"))
        target_scheduler.add_job(
            run_weather_update_job,
            trigger=CronTrigger(
                hour=hour,
                minute=minute,
                timezone=timezone,
            ),
            args=[
                job_config,
                update_callback,
                config.get("pending_job_policy", {}),
            ],
            id=job_config["id"],
            name=job_config["id"],
            replace_existing=True,
        )
        registered.append(job_config["id"])

    return registered


def refresh_scheduler(update_callback=None):
    global _update_callback

    if update_callback is not None:
        _update_callback = update_callback
    if _update_callback is None:
        raise RuntimeError("Scheduler update callback is not initialized.")

    config = get_scheduler_config()
    registered = register_scheduler_jobs(
        config,
        _update_callback,
        scheduler_instance=scheduler,
    )

    print(
        "Scheduler refreshed: "
        f"{len(registered)} enabled job(s), timezone {config['timezone']}"
    )
    return registered


def get_scheduler_runtime_status():
    jobs = []
    for job in scheduler.get_jobs():
        next_run_time = getattr(job, "next_run_time", None)
        jobs.append({
            "id": job.id,
            "next_run": (
                next_run_time.isoformat(timespec="minutes")
                if next_run_time
                else None
            ),
        })

    return {
        "running": scheduler.running,
        "registered_jobs": jobs,
    }


def start_scheduler(update_callback):
    registered = refresh_scheduler(update_callback)

    if not scheduler.running:
        scheduler.start()

    config = get_scheduler_config()
    print("Scheduler Started")
    print(f"Timezone: {config['timezone']}")
    print(f"Registered jobs: {', '.join(registered) or 'none'}")
    return scheduler
