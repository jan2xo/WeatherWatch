from workers.capture_worker import run_capture_job
from workers.image_worker import run_image_job


class WeatherWatch:
    def run(self):
        job = {
            "region": "north_luzon",
            "url": "https://www.panahon.gov.ph",
            "raw_output_path": "output/raw.png",
            "final_output_path": "output/final.png",
            "title": "WEATHERWATCH",
            "subtitle": "NORTH LUZON WEATHER UPDATE",
            "source": "Source: Panahon.gov.ph",
        }

        run_capture_job(job)
        run_image_job(job)

        print(f"Generated: {job['final_output_path']}")