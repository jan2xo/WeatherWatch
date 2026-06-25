from plugins.sources.registry import get_providers
from services.capture_services import run_capture_job
from services.image_services import run_image_job
from services.telegram_services import run_telegram_job


class WeatherWatch:
    def run(self):
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
                }

                run_capture_job(job)
                run_image_job(job)
                job["caption"] = (
                                    "📡 <b>NORTH LUZON WEATHER WATCH</b>\n\n"
                                    "General weather update ready for review.\n\n"
                                 f"{job['source']}"
                                    )
                run_telegram_job(job)

                print(f"Generated from {provider['name']}: {job['final_output_path']}")
                break

            except Exception as error:
                print(f"Provider failed: {provider['name']} → {error}")
