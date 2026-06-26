import re

from services.telegram_service import send_telegram_message
from core.telegram_listener import build_telegram_app
from core.scheduler import start_scheduler
from core.app import WeatherWatch
from config.settings import get_optional_env, validate_runtime_config
from services.admin_dashboard_service import (
    get_admin_dashboard_address,
    is_admin_dashboard_enabled,
    start_admin_dashboard_server,
)
from services.facebook_admin_service import (
    get_admin_server_address,
    start_facebook_admin_server,
)
from storage.file_retention import cleanup_manual_inputs


def same_address(left, right):
    left_host = "127.0.0.1" if left[0] == "localhost" else left[0]
    right_host = "127.0.0.1" if right[0] == "localhost" else right[0]
    return left_host == right_host and int(left[1]) == int(right[1])


def safe_error_summary(error):
    message = str(error).splitlines()[0]
    message = re.sub(r"/bot[^/\s]+/", "/bot<hidden>/", message)
    return f"{error.__class__.__name__}: {message}"


class WeatherWatchService:
    def run(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        validate_runtime_config()
        cleanup_manual_inputs()

        telegram_app = build_telegram_app()
        admin_dashboard_server = None
        facebook_admin_server = None

        dashboard_address = None
        facebook_admin_address = None

        if is_admin_dashboard_enabled():
            try:
                dashboard_address = get_admin_dashboard_address()
                admin_dashboard_server = start_admin_dashboard_server()
                print(
                    "Admin dashboard running at "
                    f"http://{dashboard_address[0]}:{dashboard_address[1]}/admin"
                )
            except Exception as error:
                print(f"Admin dashboard not started: {error}")

        if get_optional_env("FACEBOOK_REDIRECT_URI"):
            try:
                facebook_admin_address = get_admin_server_address()
            except Exception as error:
                print(f"Facebook admin reconnect server not started: {error}")

            if facebook_admin_address and not (
                admin_dashboard_server
                and dashboard_address
                and same_address(dashboard_address, facebook_admin_address)
            ):
                try:
                    facebook_admin_server = start_facebook_admin_server()
                except OSError as error:
                    print(f"Facebook admin reconnect server not started: {error}")

        weatherwatch = WeatherWatch()

        try:
            try:
                send_telegram_message("WeatherWatch bot is online. 🦾")
            except Exception as error:
                print(f"Startup Telegram notification failed: {safe_error_summary(error)}")

            start_scheduler(weatherwatch.update)

            telegram_app.run_polling(bootstrap_retries=-1)

        except KeyboardInterrupt:
            print("WeatherWatch Service stopped by user.")

        except Exception as error:
            print(f"WeatherWatch Service crashed: {safe_error_summary(error)}")

            try:
                send_telegram_message(f"WeatherWatch bot crashed. ⚠️\n\n{error}")
            except Exception:
                pass

            raise

        finally:
            if admin_dashboard_server:
                admin_dashboard_server.shutdown()

            if facebook_admin_server:
                facebook_admin_server.shutdown()

            print("WeatherWatch Service ended.")


if __name__ == "__main__":
    WeatherWatchService().run()
