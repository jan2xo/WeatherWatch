import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import helpers.browser as browser_helper
import pipelines.weather_pipeline as pipeline
import services.capture_service as capture_service


class FakePage:
    def __init__(self, events, output_mode="valid", failure_stage=None):
        self.events = events
        self.output_mode = output_mode
        self.failure_stage = failure_stage
        self.closed = False

    def goto(self, url, wait_until, timeout):
        self.events.append(("navigate", wait_until, timeout))
        if self.failure_stage == "navigation":
            raise TimeoutError("synthetic navigation timeout")

    def wait_for_function(self, expression, timeout):
        self.events.append(("ready", expression, timeout))
        if self.failure_stage == "readiness":
            raise TimeoutError("synthetic readiness timeout")

    def screenshot(self, path):
        self.events.append(("screenshot", path))
        if self.failure_stage == "screenshot":
            raise RuntimeError("synthetic screenshot failure")
        if self.output_mode == "corrupt":
            Path(path).write_bytes(b"not an image")
        else:
            Image.new("RGB", (1080, 1350), "navy").save(path)

    def close(self):
        self.closed = True
        self.events.append(("page_close",))


class FakeContext:
    def __init__(self, page, events):
        self.page = page
        self.events = events
        self.closed = False

    def new_page(self):
        self.events.append(("new_page",))
        return self.page

    def close(self):
        self.closed = True
        self.events.append(("context_close",))


class FakeBrowser:
    def __init__(self, context, events):
        self.context = context
        self.events = events
        self.closed = False

    def new_context(self, **kwargs):
        self.events.append(("new_context", kwargs))
        return self.context

    def close(self):
        self.closed = True
        self.events.append(("browser_close",))


class FakeChromium:
    def __init__(self, attempt_specs, lifecycles, events):
        self.attempt_specs = attempt_specs
        self.lifecycles = lifecycles
        self.events = events

    def launch(self, headless):
        attempt = len(self.lifecycles)
        spec = self.attempt_specs[attempt]
        self.events.append(("launch", headless))
        if spec.get("failure_stage") == "browser_start":
            self.lifecycles.append((None, None, None))
            raise RuntimeError("synthetic browser startup failure")
        page = FakePage(self.events, **spec)
        context = FakeContext(page, self.events)
        browser = FakeBrowser(context, self.events)
        self.lifecycles.append((page, context, browser))
        return browser


class FakePlaywrightContext:
    def __init__(self, chromium, events):
        self.chromium = chromium
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.events.append(("playwright_exit",))
        return False


def install_fake_playwright(attempt_specs):
    events = []
    lifecycles = []
    chromium = FakeChromium(attempt_specs, lifecycles, events)
    browser_helper.sync_playwright = lambda: FakePlaywrightContext(chromium, events)
    return events, lifecycles


def assert_closed(lifecycle):
    page, context, browser = lifecycle
    if page is not None:
        assert page.closed
        assert context.closed
        assert browser.closed


def assert_artifact_validation(temporary_directory):
    root = Path(temporary_directory)
    valid = root / "valid.png"
    Image.new("RGB", (1080, 1350), "navy").save(valid)
    result = browser_helper.validate_capture_artifact(valid)
    assert result["width"] == 1080
    assert result["height"] == 1350

    cases = {
        "missing.png": None,
        "empty.png": b"",
        "corrupt.png": b"not an image",
    }
    for name, content in cases.items():
        path = root / name
        if content is not None:
            path.write_bytes(content)
        try:
            browser_helper.validate_capture_artifact(path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} must fail artifact validation")

    tiny = root / "tiny.png"
    Image.new("RGB", (100, 100), "navy").save(tiny)
    try:
        browser_helper.validate_capture_artifact(tiny)
    except ValueError as error:
        assert "dimensions" in str(error)
    else:
        raise AssertionError("Implausibly small image must fail validation")


def assert_capture_lifecycle(temporary_directory):
    output = Path(temporary_directory) / "capture.png"
    events, lifecycles = install_fake_playwright([{}])
    attempts = browser_helper.capture_page(
        "https://www.windy.com/synthetic",
        output,
        readiness_callback=capture_service.wait_for_windy_ready,
        retry_delay_seconds=0,
    )
    assert attempts == 1
    assert output.is_file()
    assert_closed(lifecycles[0])
    event_names = [event[0] for event in events]
    assert event_names.index("ready") < event_names.index("screenshot")
    readiness_event = next(event for event in events if event[0] == "ready")
    assert "#map-container" in readiness_event[1]
    assert "#leaflet-map" in readiness_event[1]
    assert "canvas" in readiness_event[1]
    assert event_names.index("browser_close") < event_names.index("playwright_exit")

    events, lifecycles = install_fake_playwright([
        {"failure_stage": "navigation"},
        {},
    ])
    attempts = browser_helper.capture_page(
        "https://www.windy.com/synthetic",
        output,
        readiness_callback=capture_service.wait_for_windy_ready,
        retry_delay_seconds=0,
    )
    assert attempts == 2
    assert len(lifecycles) == 2
    assert all(resource.closed for lifecycle in lifecycles for resource in lifecycle)

    events, lifecycles = install_fake_playwright([
        {"output_mode": "corrupt"},
        {"output_mode": "corrupt"},
    ])
    try:
        browser_helper.capture_page(
            "https://www.windy.com/synthetic",
            output,
            readiness_callback=capture_service.wait_for_windy_ready,
            retry_delay_seconds=0,
        )
    except browser_helper.BrowserCaptureError as error:
        assert error.category == "artifact_validation"
        assert error.attempts == 2
    else:
        raise AssertionError("Corrupt capture artifacts must fail visibly")
    assert not output.exists()
    assert all(resource.closed for lifecycle in lifecycles for resource in lifecycle)

    events, lifecycles = install_fake_playwright([
        {"failure_stage": "browser_start"},
        {},
    ])
    attempts = browser_helper.capture_page(
        "https://www.windy.com/synthetic",
        output,
        readiness_callback=capture_service.wait_for_windy_ready,
        retry_delay_seconds=0,
    )
    assert attempts == 2
    assert lifecycles[0] == (None, None, None)
    assert_closed(lifecycles[1])

    events, lifecycles = install_fake_playwright([
        {"failure_stage": "readiness"},
        {"failure_stage": "readiness"},
    ])
    try:
        browser_helper.capture_page(
            "https://www.windy.com/synthetic",
            output,
            readiness_callback=capture_service.wait_for_windy_ready,
            retry_delay_seconds=0,
        )
    except browser_helper.BrowserCaptureError as error:
        assert error.category == "readiness"
        assert error.attempts == 2
        assert "synthetic" not in str(error)
        assert "windy.com" not in str(error)
    else:
        raise AssertionError("Retry exhaustion must fail visibly")
    assert not output.exists()
    assert all(resource.closed for lifecycle in lifecycles for resource in lifecycle)

    events, lifecycles = install_fake_playwright([
        {"failure_stage": "screenshot"},
        {"failure_stage": "screenshot"},
    ])
    try:
        browser_helper.capture_page(
            "https://www.windy.com/synthetic",
            output,
            readiness_callback=capture_service.wait_for_windy_ready,
            retry_delay_seconds=0,
        )
    except browser_helper.BrowserCaptureError as error:
        assert error.category == "screenshot"
        assert error.attempts == 2
    else:
        raise AssertionError("Screenshot retry exhaustion must fail visibly")
    assert all(resource.closed for lifecycle in lifecycles for resource in lifecycle)


def assert_capture_metadata():
    original = capture_service.capture_page
    job = {
        "provider": "windy",
        "url": "https://www.windy.com/synthetic",
        "raw_output_path": "unused.png",
    }
    try:
        observed = {}

        def succeed(**kwargs):
            observed.update(kwargs)
            return 2

        capture_service.capture_page = succeed
        assert capture_service.run_capture_job(job) == 2
        assert job["capture_status"] == "success"
        assert job["capture_attempts"] == 2
        assert "capture_failure_category" not in job
        assert observed["readiness_callback"] is capture_service.wait_for_windy_ready

        def fail(**_kwargs):
            raise browser_helper.BrowserCaptureError(
                "screenshot", 2, RuntimeError("secret=must-not-leak")
            )

        capture_service.capture_page = fail
        try:
            capture_service.run_capture_job(job)
        except browser_helper.BrowserCaptureError as error:
            assert "must-not-leak" not in str(error)
        else:
            raise AssertionError("Capture failure must propagate")
        assert job["capture_status"] == "failed"
        assert job["capture_attempts"] == 2
        assert job["capture_failure_category"] == "screenshot"
    finally:
        capture_service.capture_page = original


def assert_pipeline_stops_before_approval():
    originals = {
        "parse": pipeline.parse_forecast_text,
        "framing": pipeline.determine_map_framing,
        "windy": pipeline.build_windy_job_metadata,
        "capture": pipeline.run_capture_job,
        "image": pipeline.run_image_job,
        "store": pipeline.create_current_job,
        "telegram": pipeline.run_telegram_job,
    }
    events = []
    job = {
        "provider": "windy",
        "provider_display": "WINDY",
        "url": "https://www.windy.com/synthetic",
        "forecast_text": "Synthetic forecast.",
        "requested_editorial_mode": "templated",
        "raw_output_path": "unused.png",
    }
    try:
        pipeline.parse_forecast_text = lambda *_args, **_kwargs: {
            "weather_type": "general",
            "structured": {},
            "raw_text": "Synthetic forecast.",
        }
        pipeline.determine_map_framing = lambda **_kwargs: {"enabled": True}
        pipeline.build_windy_job_metadata = lambda **_kwargs: {
            "windy_url": "https://www.windy.com/synthetic"
        }
        pipeline.run_capture_job = lambda _job: (_ for _ in ()).throw(
            browser_helper.BrowserCaptureError("readiness", 2, TimeoutError())
        )
        pipeline.run_image_job = lambda _job: events.append("render")
        pipeline.create_current_job = lambda _job: events.append("approve")
        pipeline.run_telegram_job = lambda _job: events.append("telegram")
        try:
            pipeline.run_weather_pipeline(job)
        except browser_helper.BrowserCaptureError:
            pass
        else:
            raise AssertionError("Pipeline capture failure must propagate")
        assert events == []
    finally:
        pipeline.parse_forecast_text = originals["parse"]
        pipeline.determine_map_framing = originals["framing"]
        pipeline.build_windy_job_metadata = originals["windy"]
        pipeline.run_capture_job = originals["capture"]
        pipeline.run_image_job = originals["image"]
        pipeline.create_current_job = originals["store"]
        pipeline.run_telegram_job = originals["telegram"]


def assert_pipeline_success_continues():
    originals = {
        "parse": pipeline.parse_forecast_text,
        "framing": pipeline.determine_map_framing,
        "windy": pipeline.build_windy_job_metadata,
        "capture": pipeline.run_capture_job,
        "headline": pipeline.build_graphic_headline,
        "image": pipeline.run_image_job,
        "captions": pipeline.build_captions,
        "store": pipeline.create_current_job,
        "review": pipeline.build_telegram_review_caption,
        "telegram": pipeline.run_telegram_job,
    }
    events = []
    job = {
        "provider": "windy",
        "provider_display": "WINDY",
        "url": "https://www.windy.com/synthetic",
        "forecast_text": "Synthetic forecast.",
        "requested_editorial_mode": "templated",
        "raw_output_path": "unused.png",
    }
    try:
        pipeline.parse_forecast_text = lambda *_args, **_kwargs: {
            "weather_type": "general",
            "structured": {},
            "raw_text": "Synthetic forecast.",
        }
        pipeline.determine_map_framing = lambda **_kwargs: {"enabled": True}
        pipeline.build_windy_job_metadata = lambda **_kwargs: {
            "windy_url": "https://www.windy.com/synthetic"
        }
        pipeline.run_capture_job = lambda _job: events.append("capture") or 1
        pipeline.build_graphic_headline = lambda _job: "Synthetic headline"
        pipeline.run_image_job = lambda _job: events.append("render")
        pipeline.build_captions = lambda _job: {"telegram": "Synthetic caption"}
        pipeline.create_current_job = lambda stored_job: (
            events.append("approve")
            or {**stored_job, "job_id": "synthetic", "status": "pending"}
        )
        pipeline.build_telegram_review_caption = lambda *_args: "Review"
        pipeline.run_telegram_job = lambda _job: events.append("telegram")
        result = pipeline.run_weather_pipeline(job)
        assert result["status"] == "pending"
        assert events == ["capture", "render", "approve", "telegram"]
    finally:
        pipeline.parse_forecast_text = originals["parse"]
        pipeline.determine_map_framing = originals["framing"]
        pipeline.build_windy_job_metadata = originals["windy"]
        pipeline.run_capture_job = originals["capture"]
        pipeline.build_graphic_headline = originals["headline"]
        pipeline.run_image_job = originals["image"]
        pipeline.build_captions = originals["captions"]
        pipeline.create_current_job = originals["store"]
        pipeline.build_telegram_review_caption = originals["review"]
        pipeline.run_telegram_job = originals["telegram"]


def assert_windy_framing_unchanged():
    framed = capture_service.apply_windy_framing(
        "https://www.windy.com/-Satellite-satellite?satellite,11.001,125.321,5",
        {
            "enabled": True,
            "center_lat": 13.5,
            "center_lon": 122.5,
            "zoom": 7,
            "pan_x": 1.25,
            "pan_y": -3,
        },
    )
    assert framed.endswith("?satellite,10.5000,123.7500,7")


def main():
    original_playwright = browser_helper.sync_playwright
    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            assert_artifact_validation(temporary_directory)
            assert_capture_lifecycle(temporary_directory)
        assert_capture_metadata()
        assert_pipeline_stops_before_approval()
        assert_pipeline_success_continues()
        assert_windy_framing_unchanged()
    finally:
        browser_helper.sync_playwright = original_playwright
    print("WINDY capture reliability verification ok")


if __name__ == "__main__":
    main()
