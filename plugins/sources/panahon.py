PROVIDER = {
    "name": "panahon",
    "display_name": "PANaHON",
    "url": "https://www.panahon.gov.ph/",
    "shorten_url": "panahon.gov.ph",
}


class PanahonFramingError(RuntimeError):
    """PANaHON did not expose a safely controllable map view."""


WEB_MERCATOR_MAX_LATITUDE = 85.05112878


def _framing_coordinates(framing_decision):
    if not framing_decision or not framing_decision.get("enabled"):
        raise PanahonFramingError("PANaHON framing decision is unavailable")

    values = {
        key: framing_decision.get(key)
        for key in ("center_lat", "center_lon", "zoom", "pan_x", "pan_y")
    }
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool)
        for value in values.values()
    ):
        raise PanahonFramingError("PANaHON framing decision has invalid coordinates")

    latitude = values["center_lat"] + values["pan_y"]
    longitude = values["center_lon"] + values["pan_x"]
    if (
        not -WEB_MERCATOR_MAX_LATITUDE <= latitude <= WEB_MERCATOR_MAX_LATITUDE
        or not -180 <= longitude <= 180
    ):
        raise PanahonFramingError("PANaHON framing coordinates are out of range")
    if values["zoom"] <= 0:
        raise PanahonFramingError("PANaHON framing zoom is invalid")
    return latitude, longitude, values["zoom"]


def prepare_panahon_page(page, framing_decision):
    """Wait for and position PANaHON's OpenLayers map before capture.

    PANaHON's public page exposes ``window.map`` and uses EPSG:3857 for its
    OpenLayers view. The conversion is provider transport detail; the
    geographic decision remains owned by WeatherWatch's framing service.
    """
    latitude, longitude, zoom = _framing_coordinates(framing_decision)
    page.wait_for_function(
        "window.map && window.map.getView && window.map.getView() "
        "&& window.map.getSize && window.map.getSize()",
        timeout=30000,
    )
    page.evaluate(
        """
        ({latitude, longitude, zoom}) => {
            const view = window.map.getView();
            let center;
            if (window.ol && window.ol.proj && window.ol.proj.fromLonLat) {
                center = window.ol.proj.fromLonLat([longitude, latitude]);
            } else {
                const x = longitude * 20037508.34 / 180;
                const y = Math.log(Math.tan((90 + latitude) * Math.PI / 360))
                    / (Math.PI / 180) * 20037508.34 / 180;
                center = [x, y];
            }
            view.setCenter(center);
            view.setZoom(zoom);
            window.map.updateSize();
        }
        """,
        {"latitude": latitude, "longitude": longitude, "zoom": zoom},
    )


def capture_panahon_page(url, output_path, framing_decision):
    from helpers.browser import capture_page

    capture_page(
        url=url,
        output_path=output_path,
        page_setup=lambda page: prepare_panahon_page(page, framing_decision),
    )
