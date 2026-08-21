import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins.sources.panahon import PanahonFramingError, prepare_panahon_page
from services import capture_service
from services.capture_service import apply_windy_framing


DECISION = {
    "enabled": True,
    "center_lat": 13.5,
    "center_lon": 122.5,
    "zoom": 7,
    "pan_x": 1.25,
    "pan_y": -3,
}


class FakePage:
    def __init__(self):
        self.events = []

    def wait_for_function(self, expression, timeout):
        self.events.append(("wait", expression, timeout))

    def evaluate(self, expression, values):
        self.events.append(("apply", expression, values))


def main():
    page = FakePage()
    prepare_panahon_page(page, DECISION)
    assert [event[0] for event in page.events] == ["wait", "apply"]
    readiness = page.events[0][1]
    assert "window.map.getSize" in readiness
    assert "window.map.getView().getSize" not in readiness
    values = page.events[-1][2]
    assert values == {"latitude": 10.5, "longitude": 123.75, "zoom": 7}
    assert "setCenter" in page.events[-1][1]
    assert "setZoom" in page.events[-1][1]

    for invalid in (
        {},
        {**DECISION, "center_lat": None},
        {**DECISION, "pan_x": "bad"},
        {**DECISION, "center_lat": 100},
        {**DECISION, "center_lat": 90},
        {**DECISION, "center_lon": 181},
    ):
        try:
            prepare_panahon_page(FakePage(), invalid)
        except PanahonFramingError:
            pass
        else:
            raise AssertionError("invalid PANaHON framing was accepted")

    # The provider callback is isolated; WINDY's existing URL adapter remains
    # unchanged and retains its documented center-plus-pan semantics.
    assert apply_windy_framing(
        "https://www.windy.com/-Satellite-satellite?satellite,11.001,125.321,5",
        DECISION,
    ).endswith("?satellite,10.5000,123.7500,7")

    calls = []
    original = capture_service.capture_panahon_page
    capture_service.capture_panahon_page = lambda **kwargs: calls.append(kwargs)
    try:
        decision = dict(DECISION)
        capture_service.run_capture_job({
            "provider": "panahon",
            "url": "https://www.panahon.gov.ph/",
            "raw_output_path": "output/panahon.png",
            "framing_decision": decision,
        })
        assert calls and calls[0]["framing_decision"] is decision
        assert decision["provider_framing_applied"] is True
        assert decision["provider_framing_status"] == "applied"
    finally:
        capture_service.capture_panahon_page = original

    original = capture_service.capture_panahon_page
    capture_service.capture_panahon_page = lambda **kwargs: (_ for _ in ()).throw(
        PanahonFramingError("map was not ready")
    )
    try:
        decision = dict(DECISION)
        try:
            capture_service.run_capture_job({
                "provider": "panahon",
                "url": "https://www.panahon.gov.ph/",
                "raw_output_path": "output/panahon.png",
                "framing_decision": decision,
            })
        except PanahonFramingError:
            pass
        else:
            raise AssertionError("PANaHON framing failure must propagate")
        assert decision["provider_framing_applied"] is False
        assert decision["provider_framing_status"] == "degraded"
        assert decision["provider_framing_reason"] == "map was not ready"
    finally:
        capture_service.capture_panahon_page = original


if __name__ == "__main__":
    main()
