from services.telegram_service import send_telegram_message
from core.telegram_listener import build_telegram_app
from core.scheduler import start_scheduler
from core.app import WeatherWatch
from config.settings import get_optional_env, validate_runtime_config
from services.facebook_admin_service import start_facebook_admin_server
from storage.file_retention import cleanup_manual_inputs


class WeatherWatchService:
    def run(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        validate_runtime_config()
        cleanup_manual_inputs()

        telegram_app = build_telegram_app()
        facebook_admin_server = None

        if get_optional_env("FACEBOOK_REDIRECT_URI"):
            try:
                facebook_admin_server = start_facebook_admin_server()
            except OSError as error:
                print(f"Facebook admin reconnect server not started: {error}")

        weatherwatch = WeatherWatch()

        try:
            try:
                send_telegram_message("WeatherWatch bot is online. 🦾")
            except Exception as error:
                print(f"Startup Telegram notification failed: {error}")

            start_scheduler(weatherwatch.update)

            telegram_app.run_polling()

        except KeyboardInterrupt:
            print("WeatherWatch Service stopped by user.")

        except Exception as error:
            print(f"WeatherWatch Service crashed: {error}")

            try:
                send_telegram_message(f"WeatherWatch bot crashed. ⚠️\n\n{error}")
            except Exception:
                pass

            raise

        finally:
            if facebook_admin_server:
                facebook_admin_server.shutdown()

            print("WeatherWatch Service ended.")
