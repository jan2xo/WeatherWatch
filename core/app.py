from helpers.browser import capture_page
from helpers.image import compose_weather_card


class WeatherWatch:
    def run(self):
        raw_path = "output/raw.png"
        final_path = "output/final.png"

        capture_page(
            url="https://www.panahon.gov.ph/",
            output_path=raw_path
        )

        compose_weather_card(
            input_path=raw_path,
            output_path=final_path,
            title="WEATHERWATCH",
            subtitle="NORTH LUZON WEATHER UPDATE"
        )

        print(f"Generated: {final_path}")