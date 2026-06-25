from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo


scheduler = BackgroundScheduler(
    timezone=ZoneInfo("Asia/Manila")
)


def start_scheduler(update_callback):
    scheduler.add_job(
        update_callback,
        trigger="cron",
        hour="5,8,11,14,17,20,23",
        minute=5,
        id="weather_update",
        replace_existing=True,
    )

    scheduler.start()

    print("Scheduler Started (Asia/Manila)")
    print("Runs daily at: 05:05, 08:05, 11:05, 14:05, 17:05, 20:05, 23:05")