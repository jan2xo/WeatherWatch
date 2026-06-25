import requests
from bs4 import BeautifulSoup


PAGASA_URL = "https://www.pagasa.dost.gov.ph/weather"


def fetch_daily_forecast():
    response = requests.get(
        PAGASA_URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    panels = soup.select(".panel")

    for panel in panels:

        heading = panel.select_one(".panel-heading")

        if not heading:
            continue

        title = heading.get_text(strip=True)

        if title.lower() != "synopsis":
            continue

        body = panel.select_one(".panel-body")

        if not body:
            continue

        paragraph = body.find("p")

        if paragraph:
            return paragraph.get_text(" ", strip=True)

    raise RuntimeError("Synopsis section not found.")