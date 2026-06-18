from pathlib import Path
from playwright.sync_api import sync_playwright


def capture_page(url, output_path):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1080, "height": 1350}
        )

        page.goto(url)

        page.screenshot(path=output_path)

        browser.close()