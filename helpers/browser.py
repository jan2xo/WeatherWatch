from pathlib import Path
from playwright.sync_api import sync_playwright


def capture_page(url, output_path, page_setup=None):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1080, "height": 1350},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148 Safari/537.36",
        )

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        if page_setup is not None:
            page_setup(page)
        page.screenshot(path=output_path)

        browser.close()
