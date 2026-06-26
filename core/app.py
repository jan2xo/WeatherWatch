from plugins.sources.registry import get_providers
from pipelines.weather_pipeline import run_weather_pipeline
from services.pagasa_service import fetch_daily_forecast
from storage.approval_store import get_current_job


class WeatherWatch:

    def update(self):
        current_job = get_current_job()

        if current_job:
            print(
                "Weather update skipped: "
                f"current job {current_job.get('job_id')} is {current_job.get('status')}"
            )
            return {
                "skipped": True,
                "reason": "current_job_exists",
                "current_job": current_job,
            }

        providers = get_providers()
        last_error = None

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

                current_job = run_weather_pipeline(job)

                print(f"Queued for approval: {job['final_output_path']}")
                return current_job

            except Exception as error:
                last_error = error
                print(f"Provider failed: {provider['name']} → {error}")

        if last_error:
            raise last_error

        raise RuntimeError("No weather providers are configured.")
