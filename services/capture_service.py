from urllib.parse import urlsplit, urlunsplit

from helpers.browser import BrowserCaptureError, capture_page


WINDY_READINESS_EXPRESSION = """() => {
    if (document.readyState !== 'complete') return false;
    const container = document.querySelector('#map-container');
    const map = document.querySelector('#leaflet-map');
    if (!container || !map) return false;
    const containerRect = container.getBoundingClientRect();
    const mapRect = map.getBoundingClientRect();
    if (containerRect.width <= 0 || containerRect.height <= 0 ||
        mapRect.width <= 0 || mapRect.height <= 0) return false;
    const renderedLayer = map.querySelector(
        'canvas, img.leaflet-tile-loaded, .leaflet-tile-loaded'
    );
    if (!renderedLayer) return false;
    const layerRect = renderedLayer.getBoundingClientRect();
    return layerRect.width > 0 && layerRect.height > 0;
}"""
WINDY_PAINT_SETTLE_MS = 10000


def wait_for_windy_ready(page, timeout_ms):
    page.wait_for_function(WINDY_READINESS_EXPRESSION, timeout=timeout_ms)
    page.wait_for_timeout(WINDY_PAINT_SETTLE_MS)


def apply_windy_framing(url, framing_decision):
    if not framing_decision or not framing_decision.get("enabled"):
        return url

    latitude = framing_decision.get("center_lat")
    longitude = framing_decision.get("center_lon")
    zoom = framing_decision.get("zoom")
    pan_x = framing_decision.get("pan_x", 0)
    pan_y = framing_decision.get("pan_y", 0)

    if latitude is None or longitude is None or zoom is None:
        return url

    if (
        not isinstance(pan_x, (int, float))
        or isinstance(pan_x, bool)
        or not isinstance(pan_y, (int, float))
        or isinstance(pan_y, bool)
    ):
        return url

    framed_latitude = latitude + pan_y
    framed_longitude = longitude + pan_x

    if not (-90 <= framed_latitude <= 90):
        return url
    if not (-180 <= framed_longitude <= 180):
        return url

    parsed = urlsplit(url)
    query_parts = parsed.query.split(",")

    if len(query_parts) < 4:
        return url

    query = ",".join([
        query_parts[0],
        f"{framed_latitude:.4f}",
        f"{framed_longitude:.4f}",
        str(zoom),
    ])
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        query,
        parsed.fragment,
    ))


def resolve_capture_url(job):
    url = job["url"]

    if (job.get("provider") or "").lower() == "windy":
        if job.get("windy_url"):
            return job["windy_url"]
        return apply_windy_framing(url, job.get("framing_decision"))

    return url


def run_capture_job(job):
    readiness_callback = None
    if (job.get("provider") or "").lower() == "windy":
        readiness_callback = wait_for_windy_ready

    try:
        attempts = capture_page(
            url=resolve_capture_url(job),
            output_path=job["raw_output_path"],
            readiness_callback=readiness_callback,
        )
    except BrowserCaptureError as error:
        job["capture_status"] = "failed"
        job["capture_attempts"] = error.attempts
        job["capture_failure_category"] = error.category
        raise

    job["capture_status"] = "success"
    job["capture_attempts"] = attempts
    job.pop("capture_failure_category", None)
    return attempts
