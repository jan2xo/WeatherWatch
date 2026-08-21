import os
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.admin_dashboard_service as dashboard
import storage.approval_store as approval_store
from services.ai_editorial_fallback import generate_with_fallback
from services.content_composer_service import compose_weather_content
from services.editorial_memory_service import (
    EditorialMemoryItem,
    retrieve_relevant_memory,
)
from services.editorial_mode_service import EditorialMode, select_editorial_mode
from services.forecast_parser import parse_pagasa_forecast_text


class SyntheticProvider:
    def __init__(self, name, payload):
        self.name = name
        self.payload = payload
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        return dict(self.payload)


def main():
    original_state_file = approval_store.STATE_FILE
    environment = {
        name: os.environ.get(name)
        for name in (
            "FACEBOOK_PAGE_ID",
            "FACEBOOK_PAGE_ACCESS_TOKEN",
        )
    }

    try:
        with tempfile.TemporaryDirectory() as directory:
            approval_store.STATE_FILE = Path(directory) / "approval_state.json"
            os.environ["FACEBOOK_PAGE_ID"] = "synthetic-page"
            os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "synthetic-token"

            bulletin = (
                'At 5:00 PM, the center of Typhoon "SYNTHETIC" was located '
                "at 100 km East of Cagayan (18.0°N, 122.0°E). Maximum sustained "
                "winds of 80 km/h near the center and gustiness of up to 100 km/h."
            )
            facts = parse_pagasa_forecast_text(bulletin)
            assert facts["maximum_sustained_winds_kmh"] == 80

            templated = compose_weather_content(bulletin, facts)
            assert templated["headline"]
            assert templated["summary"]
            assert select_editorial_mode(
                "automatic", ai_available=False
            ) is EditorialMode.TEMPLATED

            memory = retrieve_relevant_memory(
                [
                    EditorialMemoryItem(
                        "approved-typhoon", "Approved wording", frozenset({"typhoon"})
                    ),
                    EditorialMemoryItem(
                        "not-approved", "Do not use", frozenset({"typhoon"}), False
                    ),
                ],
                tags=["typhoon"],
                limit=1,
            )
            assert [item.memory_id for item in memory] == ["approved-typhoon"]

            context = {
                "weather_facts": {"maximum_sustained_winds_kmh": 80},
                "memory_references": [item.memory_id for item in memory],
            }
            rejected = SyntheticProvider(
                "synthetic-primary",
                {
                    "headline": "Unsafe draft",
                    "caption": "Winds reach 999 km/h.",
                    "generation_mode": "ai_assisted",
                    "model": "synthetic-model",
                },
            )
            accepted = SyntheticProvider(
                "synthetic-fallback",
                {
                    "headline": "Validated draft",
                    "caption": "Winds reach 80 km/h.",
                    "generation_mode": "ai_assisted",
                    "model": "synthetic-model",
                    "memory_references": ["approved-typhoon"],
                },
            )
            draft, provenance = generate_with_fallback(
                [rejected, accepted], context
            )
            assert draft.provider == "synthetic-fallback"
            assert provenance.fallback_level == 1
            assert provenance.validation_state == "valid"
            assert rejected.calls == 1 and accepted.calls == 1

            approval_store.create_current_job(
                {
                    "job_id": "synthetic-certification",
                    "headline": draft.headline,
                    "caption": draft.caption,
                    "captions": {"facebook": draft.caption},
                    "requested_editorial_mode": "automatic",
                    "editorial_mode": "ai_assisted",
                    "ai_status": "available",
                    "ai_provider": draft.provider,
                    "ai_model": draft.model,
                    "ai_fallback_level": provenance.fallback_level,
                    "ai_validation_state": provenance.validation_state,
                    "editorial_provenance": {
                        "provider": provenance.provider,
                        "fallback_level": provenance.fallback_level,
                    },
                }
            )
            restarted_job = approval_store.load_state()["current"]
            assert restarted_job["job_id"] == "synthetic-certification"
            assert restarted_job["ai_fallback_level"] == 1
            approval_store.mark_current_publish_failed("synthetic failure")
            assert approval_store.load_state()["current"]["status"] == "publish_failed"

            health = dashboard.build_health_payload()
            assert health["application_alive"] is True
            assert health["current_job_id"] == "synthetic-certification"
            assert health["editorial_subsystem"]["templated_available"] is True
            assert "synthetic-token" not in str(health)

    finally:
        approval_store.STATE_FILE = original_state_file
        for name, value in environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("integrated synthetic certification verification ok")


if __name__ == "__main__":
    main()
