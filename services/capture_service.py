from urllib.parse import urlsplit, urlunsplit

from helpers.browser import capture_page


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
        return apply_windy_framing(url, job.get("framing_decision"))

    return url


def run_capture_job(job):
    return capture_page(
        url=resolve_capture_url(job),
        output_path=job["raw_output_path"],
    )
