from helpers.browser import capture_page


class WeatherWatch:

    def run(self):

        capture_page(
            url="https://www.panahon.gov.ph/",
            output_path="output/test.png"
        )