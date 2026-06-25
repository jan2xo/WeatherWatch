from services.telegram_service import send_telegram_message
from core.telegram_listener import build_telegram_app
from core.scheduler import start_scheduler
from core.app import WeatherWatch


class WeatherWatchService:
    def run(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        telegram_app = build_telegram_app()
        weatherwatch = WeatherWatch()

        try:
            send_telegram_message("WeatherWatch bot is online. 🦾")

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
            print("WeatherWatch Service ended.")