from plugins.sources.registry import get_providers
from pipelines.weather_pipeline import run_weather_pipeline
from services.pagasa_service import fetch_daily_forecast
from services.editorial_mode_service import EditorialMode
from config.settings import get_optional_env
from storage.approval_store import get_current_job


class WeatherWatch:

    def update(self, requested_editorial_mode=None):
        requested_mode = requested_editorial_mode or get_optional_env(
            "WEATHERWATCH_EDITORIAL_MODE"
        ) or EditorialMode.TEMPLATED.value
        try:
            requested_enum = EditorialMode(requested_mode)
        except ValueError as error:
            raise ValueError(f"Unsupported editorial mode: {requested_mode!r}") from error
        resolved_mode = (
            EditorialMode.TEMPLATED
            if requested_enum is EditorialMode.TEMPLATED
            else requested_enum
        )
        ai_status = "not_requested" if requested_enum is EditorialMode.TEMPLATED else "pending"
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
                        "requested_editorial_mode": str(requested_mode),
                        "editorial_mode": resolved_mode.value,
                        "ai_status": ai_status,
                        "ai_provider": None,
                        "ai_model": None,
                        "ai_fallback_level": None,
                        "ai_validation_state": "not_run",
                        "editorial_provenance": {
                            "mode": resolved_mode.value,
                            "status": ai_status,
                        },
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
