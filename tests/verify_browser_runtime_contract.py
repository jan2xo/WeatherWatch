import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.runtime_paths import runtime_path
import helpers.browser as browser_helper
from services.capture_service import WINDY_PAINT_SETTLE_MS, wait_for_windy_ready


class FakePage:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def goto(self, _url, *, wait_until, timeout):
        self.events.append(("navigation", wait_until, timeout))

    def wait_for_function(self, expression, *, timeout):
        self.events.append(("structural_readiness", expression, timeout))

    def wait_for_timeout(self, timeout):
        self.events.append(("paint_settle", timeout))

    def screenshot(self, *, path, timeout):
        self.events.append(("screenshot", str(path), timeout))
        Image.new("RGB", (1080, 1350), "navy").save(path)

    def close(self):
        self.closed = True
        self.events.append(("page_close",))


class FakeContext:
    def __init__(self, events, page):
        self.events = events
        self.page = page
        self.closed = False

    def new_page(self):
        self.events.append(("new_page",))
        return self.page

    def close(self):
        self.closed = True
        self.events.append(("context_close",))


class FakeBrowser:
    def __init__(self, events, context):
        self.events = events
        self.context = context
        self.closed = False

    def new_context(self, **options):
        self.events.append(("new_context", options))
        return self.context

    def close(self):
        self.closed = True
        self.events.append(("browser_close",))


class FakeChromium:
    def __init__(self, events, browser):
        self.events = events
        self.browser = browser

    def launch(self, **options):
        self.events.append(("launch", options))
        return self.browser


class FakePlaywright:
    def __init__(self, events, chromium):
        self.events = events
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.events.append(("playwright_exit",))


def test_managed_runtime_capture_contract():
    original_playwright = browser_helper.sync_playwright
    original_root = os.environ.get("WEATHERWATCH_RUNTIME_ROOT")
    with tempfile.TemporaryDirectory() as directory:
        events = []
        page = FakePage(events)
        context = FakeContext(events, page)
        browser = FakeBrowser(events, context)
        chromium = FakeChromium(events, browser)
        browser_helper.sync_playwright = lambda: FakePlaywright(events, chromium)
        os.environ["WEATHERWATCH_RUNTIME_ROOT"] = directory
        output_path = runtime_path("output/windy_raw.png")
        try:
            result = browser_helper.capture_page(
                "https://www.windy.com/synthetic",
                output_path,
                readiness_callback=wait_for_windy_ready,
                retry_delay_seconds=0,
            )
        finally:
            browser_helper.sync_playwright = original_playwright
            if original_root is None:
                os.environ.pop("WEATHERWATCH_RUNTIME_ROOT", None)
            else:
                os.environ["WEATHERWATCH_RUNTIME_ROOT"] = original_root

    assert result == 1
    launch = next(event for event in events if event[0] == "launch")
    assert launch[1] == {
        "headless": True,
        "timeout": browser_helper.DEFAULT_BROWSER_START_TIMEOUT_MS,
    }
    assert "args" not in launch[1]
    assert "--no-sandbox" not in str(launch)

    context_event = next(event for event in events if event[0] == "new_context")
    assert context_event[1]["viewport"] == {"width": 1080, "height": 1350}
    assert context_event[1]["user_agent"] == browser_helper.CAPTURE_USER_AGENT

    screenshot = next(event for event in events if event[0] == "screenshot")
    assert screenshot[2] == browser_helper.DEFAULT_SCREENSHOT_TIMEOUT_MS

    names = [event[0] for event in events]
    assert names.index("navigation") < names.index("structural_readiness")
    assert names.index("structural_readiness") < names.index("paint_settle")
    assert names.index("paint_settle") < names.index("screenshot")
    assert next(event for event in events if event[0] == "paint_settle")[1] == 10000
    assert WINDY_PAINT_SETTLE_MS == 10000
    assert names.index("page_close") < names.index("playwright_exit")
    assert names.index("context_close") < names.index("playwright_exit")
    assert names.index("browser_close") < names.index("playwright_exit")
    assert page.closed and context.closed and browser.closed


def assert_invalid_bounds(**overrides):
    arguments = {
        "url": "https://www.windy.com/synthetic",
        "output_path": "unused.png",
        "attempts": 1,
        "retry_delay_seconds": 0,
        "browser_start_timeout_ms": 1,
        "navigation_timeout_ms": 1,
        "readiness_timeout_ms": 1,
        "screenshot_timeout_ms": 1,
    }
    arguments.update(overrides)
    try:
        browser_helper.capture_page(**arguments)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Invalid capture bounds were accepted: {overrides!r}")


def test_all_capture_controls_are_finite_and_bounded():
    for attempts in (0, -1, True, 6):
        assert_invalid_bounds(attempts=attempts)
    for timeout in (0, -1, True, 120001):
        assert_invalid_bounds(browser_start_timeout_ms=timeout)
    for timeout in (0, -1, True, 300001):
        assert_invalid_bounds(navigation_timeout_ms=timeout)
    for timeout in (0, -1, True, 120001):
        assert_invalid_bounds(readiness_timeout_ms=timeout)
    for timeout in (0, -1, True, 120001):
        assert_invalid_bounds(screenshot_timeout_ms=timeout)
    for delay in (-1, True, float("inf"), 31):
        assert_invalid_bounds(retry_delay_seconds=delay)


def main():
    test_managed_runtime_capture_contract()
    test_all_capture_controls_are_finite_and_bounded()
    print("browser runtime contract verification ok")


if __name__ == "__main__":
    main()
