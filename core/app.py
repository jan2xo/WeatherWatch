from plugins.sources.registry import get_providers
from workers.capture_worker import run_capture_job
from workers.image_worker import run_image_job


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
                    "title": "WEATHERWATCH",
                    "subtitle": "NORTH LUZON WEATHER UPDATE",
                    "source": f"Source: {provider['name']}",
                }

                run_capture_job(job)
                run_image_job(job)

                print(f"Generated from {provider['name']}: {job['final_output_path']}")
                break

            except Exception as error:
                print(f"Provider failed: {provider['name']} → {error}")