from plugins.sources.registry import get_providers
from pipelines.weather_pipeline import run_weather_pipeline
from services.pagasa_service import fetch_daily_forecast


class WeatherWatch:

    def update(self):
        providers = get_providers()

        for provider in providers:
            try:
                job = {
                        "region": "north_luzon",
                        "provider": provider["name"],
                        "provider_display": provider["display_name"],
                        "provider_url": provider["shorten_url"],
                        "url": provider["url"],
                        "raw_output_path": f"output/{provider['name']}_raw.png",
                        "final_output_path": f"output/{provider['name']}_final.png",
                        "headline": "MAINIT AT MAALINSANGANG PANAHON, MAY PAMINSAN-MINSANG PAG-ULAN",
                        "source": (
                                    f"MAP: {provider['display_name'].upper()} | {provider['shorten_url']}\n"
                                    f"FORECAST: PAGASA | pagasa.dost.gov.ph"
                                ),
                        "forecast_text": fetch_daily_forecast(),
                    }

                run_weather_pipeline(job)

                print(f"Queued for approval: {job['final_output_path']}")
                return

            except Exception as error:
                print(f"Provider failed: {provider['name']} → {error}")