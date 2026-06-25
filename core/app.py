from plugins.sources.registry import get_providers
from pipelines.weather_pipeline import run_weather_pipeline


class WeatherWatch:

    def update(self):
        providers = get_providers()

        for provider in providers:
            try:
                job = {
                    "region": "north_luzon",
                    "provider": provider["name"],
                    "url": provider["url"],
                    "raw_output_path": f"output/{provider['name']}_raw.png",
                    "final_output_path": f"output/{provider['name']}_final.png",
                    "headline": "MAINIT AT MAALINSANGANG PANAHON, MAY PAMINSAN-MINSANG PAG-ULAN",
                    "source": f"DATA: {provider['display_name']} | {provider['shorten_url']}",
                    "forecast_text": (
                                        'At 3:00 PM today, the center of Severe Tropical Storm "FRANCISCO" '
                                        '{MEKKHALA} was estimated based on all available data at 620 km '
                                        'Northeast of Itbayat, Batanes. Meanwhile, the center of Tropical '
                                        'Storm "GARDO" {HIGOS} was estimated based on all available data at '
                                        '1,420 km East of Extreme Northern Luzon. Southwest Monsoon affecting '
                                        'Luzon and Visayas.'
                                        ),
                }

                run_weather_pipeline(job)

                print(f"Queued for approval: {job['final_output_path']}")
                return

            except Exception as error:
                print(f"Provider failed: {provider['name']} → {error}")