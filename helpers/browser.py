import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from playwright.sync_api import sync_playwright


DEFAULT_CAPTURE_ATTEMPTS = 2
DEFAULT_NAVIGATION_TIMEOUT_MS = 60000
DEFAULT_READINESS_TIMEOUT_MS = 20000
DEFAULT_RETRY_DELAY_SECONDS = 0.5
MIN_SCREENSHOT_WIDTH = 320
MIN_SCREENSHOT_HEIGHT = 240


class BrowserCaptureError(RuntimeError):
    def __init__(self, category, attempts, cause=None):
        cause_name = type(cause).__name__ if cause is not None else "unknown error"
        super().__init__(
            f"Capture failed after {attempts} attempt(s) during "
            f"{category} ({cause_name})."
        )
        self.category = category
        self.attempts = attempts


def validate_capture_artifact(output_path):
    path = Path(output_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Screenshot artifact is missing or empty.")

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("Screenshot artifact is not a readable image.") from error

    if width < MIN_SCREENSHOT_WIDTH or height < MIN_SCREENSHOT_HEIGHT:
        raise ValueError("Screenshot artifact dimensions are implausibly small.")

    return {"width": width, "height": height, "bytes": path.stat().st_size}


def _remove_partial_artifact(output_path):
    try:
        Path(output_path).unlink(missing_ok=True)
    except OSError:
        # A cleanup failure must not replace the original capture failure.
        pass


def _close_safely(resource):
    if resource is None:
        return
    try:
        resource.close()
    except Exception:
        pass


def capture_page(
    url,
    output_path,
    readiness_callback=None,
    attempts=DEFAULT_CAPTURE_ATTEMPTS,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    navigation_timeout_ms=DEFAULT_NAVIGATION_TIMEOUT_MS,
    readiness_timeout_ms=DEFAULT_READINESS_TIMEOUT_MS,
):
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise ValueError("Capture attempts must be a positive integer.")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    last_category = "browser_start"

    for attempt in range(1, attempts + 1):
        _remove_partial_artifact(output_path)
        browser = None
        context = None
        page = None
        stage = "browser_start"

        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={"width": 1080, "height": 1350},
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 Chrome/148 Safari/537.36"
                        ),
                    )
                    page = context.new_page()

                    stage = "navigation"
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=navigation_timeout_ms,
                    )

                    stage = "readiness"
                    if readiness_callback is not None:
                        readiness_callback(page, readiness_timeout_ms)
                    else:
                        page.wait_for_function(
                            """() => document.readyState === 'complete' &&
                                document.body &&
                                document.body.getBoundingClientRect().width > 0 &&
                                document.body.getBoundingClientRect().height > 0""",
                            timeout=readiness_timeout_ms,
                        )

                    stage = "screenshot"
                    page.screenshot(path=output_path)

                    stage = "artifact_validation"
                    validate_capture_artifact(output_path)
                    return attempt
                finally:
                    _close_safely(page)
                    _close_safely(context)
                    _close_safely(browser)
        except Exception as error:
            last_error = error
            last_category = stage
            _remove_partial_artifact(output_path)

        if attempt < attempts and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)

    raise BrowserCaptureError(
        category=last_category,
        attempts=attempts,
        cause=last_error,
    ) from last_error
