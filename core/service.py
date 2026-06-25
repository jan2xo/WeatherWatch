from services.telegram_service import send_telegram_message
from core.telegram_listener import build_telegram_app


class WeatherWatchService:
    def run(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        telegram_app = build_telegram_app()

        try:
            send_telegram_message("WeatherWatch bot is online. 🦾")
            telegram_app.run_polling()

        except Exception as error:
            print(f"WeatherWatch Service crashed: {error}")

            try:
                send_telegram_message(f"WeatherWatch bot crashed. ⚠️\n\n{error}")
            except Exception:
                pass

            raise

        finally:
            print("WeatherWatch Service ended.")

            try:
                send_telegram_message("WeatherWatch bot stopped. 🛑")
            except Exception:
                pass