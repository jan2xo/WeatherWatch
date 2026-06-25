from core.telegram_listener import build_telegram_app


class WeatherWatchService:
    def start(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        telegram_app = build_telegram_app()
        telegram_app.run_polling()