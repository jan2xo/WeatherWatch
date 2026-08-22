import sys
import threading
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.service as service


class FakeServer:
    def __init__(self, name, events, block_shutdown=False):
        self.name = name
        self.events = events
        self.daemon_threads = False
        self.block_shutdown = block_shutdown
        self.release_shutdown = threading.Event()

    def shutdown(self):
        self.events.append(f"{self.name}.shutdown")
        if self.block_shutdown:
            self.release_shutdown.wait()

    def server_close(self):
        self.events.append(f"{self.name}.close")


class FakeScheduler:
    def __init__(self, events):
        self.events = events
        self.running = True

    def shutdown(self, wait=True):
        self.events.append(f"scheduler.shutdown:{wait}")
        self.running = False


class FakeTelegramApp:
    def __init__(self, events, polling_result=None):
        self.events = events
        self.polling_result = polling_result

    def run_polling(self, **kwargs):
        self.events.append(f"telegram.poll:{kwargs['bootstrap_retries']}")
        self.events.append(
            "telegram.signals:"
            + ",".join(str(value) for value in kwargs["stop_signals"])
        )
        if self.polling_result:
            raise self.polling_result


def exercise_service(
    polling_result=None,
    weatherwatch_error=None,
    dashboard_error=None,
    managed_port=None,
):
    events = []
    dashboard = FakeServer("dashboard", events)
    facebook = FakeServer("facebook", events)
    scheduler = FakeScheduler(events)
    telegram = FakeTelegramApp(events, polling_result)

    originals = {
        name: getattr(service, name)
        for name in (
            "validate_runtime_config",
            "cleanup_manual_inputs",
            "build_telegram_app",
            "is_admin_dashboard_enabled",
            "get_admin_dashboard_address",
            "start_admin_dashboard_server",
            "get_optional_env",
            "get_admin_server_address",
            "start_facebook_admin_server",
            "WeatherWatch",
            "send_telegram_message",
            "start_scheduler",
        )
    }

    class FakeWeatherWatch:
        def __init__(self):
            events.append("weatherwatch.init")
            if weatherwatch_error:
                raise weatherwatch_error

        def update(self):
            return None

    try:
        service.validate_runtime_config = lambda: events.append("config.validate")
        service.cleanup_manual_inputs = lambda: events.append("inputs.cleanup")
        service.build_telegram_app = lambda: events.append("telegram.build") or telegram
        service.is_admin_dashboard_enabled = lambda: True
        service.get_admin_dashboard_address = lambda: ("127.0.0.1", 8787)
        def start_dashboard():
            events.append("dashboard.start")
            if dashboard_error:
                raise dashboard_error
            return dashboard

        service.start_admin_dashboard_server = start_dashboard
        service.get_optional_env = (
            lambda name: "http://127.0.0.1:8790/admin/fb/callback"
            if name == "FACEBOOK_REDIRECT_URI"
            else managed_port if name == "PORT" else None
        )
        service.get_admin_server_address = lambda: ("127.0.0.1", 8790)
        service.start_facebook_admin_server = (
            lambda: events.append("facebook.start") or facebook
        )
        service.WeatherWatch = FakeWeatherWatch
        service.send_telegram_message = (
            lambda message: events.append(f"telegram.send:{message}")
        )
        service.start_scheduler = (
            lambda callback: events.append("scheduler.start") or scheduler
        )

        caught = None
        try:
            service.WeatherWatchService().run()
        except Exception as error:
            caught = error
        return events, dashboard, facebook, scheduler, caught
    finally:
        for name, value in originals.items():
            setattr(service, name, value)


def main():
    events, dashboard, facebook, scheduler, caught = exercise_service(
        polling_result=KeyboardInterrupt(),
    )
    assert caught is None
    assert scheduler.running is False
    assert dashboard.daemon_threads is True
    assert facebook.daemon_threads is True
    assert "telegram.signals:2,15" in events
    assert events.index("scheduler.shutdown:False") < events.index("facebook.shutdown")
    assert events.index("facebook.close") < events.index("dashboard.shutdown")
    assert events[-1] == "dashboard.close"

    # A startup failure after both HTTP servers exist must still release them.
    startup_error = RuntimeError("startup failed /botSECRET/value")
    events, _, _, scheduler, caught = exercise_service(
        weatherwatch_error=startup_error,
    )
    assert caught is startup_error
    assert "scheduler.start" not in events
    assert "facebook.shutdown" in events
    assert "facebook.close" in events
    assert "dashboard.shutdown" in events
    assert "dashboard.close" in events
    crash_messages = [
        event for event in events if event.startswith("telegram.send:WeatherWatch bot crashed")
    ]
    assert len(crash_messages) == 1
    assert "SECRET" not in crash_messages[0]
    assert "/bot<hidden>/" in crash_messages[0]

    # A managed web service must fail fast if it cannot bind the platform port.
    events, _, _, _, caught = exercise_service(
        dashboard_error=OSError("bind failed"),
        managed_port="10000",
    )
    assert isinstance(caught, RuntimeError)
    assert str(caught) == "Managed-runtime HTTP server failed to start."
    assert "scheduler.start" not in events

    # HTTPServer.shutdown() is documented to wait for serve_forever(). A
    # partial-start server must not make the managed process wait forever.
    blocking_events = []
    blocking_server = FakeServer(
        "partial",
        blocking_events,
        block_shutdown=True,
    )
    assert service.shutdown_http_server(
        blocking_server,
        "Partial server",
        timeout=0.01,
    ) is False
    assert blocking_events == ["partial.shutdown", "partial.close"]
    blocking_server.release_shutdown.set()

    # Idempotent cleanup accepts features that never started.
    assert service.shutdown_http_server(None, "unused") is True
    assert service.shutdown_scheduler(None) is True
    assert service.dashboard_handles_facebook_callback(
        object(), "https://weatherwatch.example/admin/fb/callback"
    ) is True
    assert service.dashboard_handles_facebook_callback(
        object(), "http://127.0.0.1:8790/admin/fb/callback"
    ) is False
    assert service.dashboard_handles_facebook_callback(
        object(), "https://weatherwatch.example/wrong/callback"
    ) is False

    print("service lifecycle verification ok")


if __name__ == "__main__":
    main()
