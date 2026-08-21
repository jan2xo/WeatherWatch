import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pipelines.weather_pipeline as pipeline
from services.ai_editorial_service import AIEditorialDraft


def _base_job(mode):
    return {
        "provider": "synthetic",
        "provider_display": "Synthetic",
        "provider_url": "https://example.invalid",
        "url": "https://example.invalid",
        "raw_output_path": "output/raw.png",
        "final_output_path": "output/final.png",
        "source": "Forecast: PAGASA",
        "forecast_text": "Sunny conditions.",
        "requested_editorial_mode": mode,
        "editorial_mode": mode,
    }


def main():
    original = {
        "capture": pipeline.run_capture_job,
        "image": pipeline.run_image_job,
        "telegram": pipeline.run_telegram_job,
        "framing": pipeline.determine_map_framing,
        "captions": pipeline.build_captions,
        "store": pipeline.create_current_job,
        "generate": pipeline.generate_ai_editorial,
    }
    try:
        pipeline.run_capture_job = lambda job: None
        pipeline.run_image_job = lambda job: None
        pipeline.run_telegram_job = lambda job: None
        pipeline.determine_map_framing = lambda **kwargs: {"strategy": "synthetic"}
        pipeline.build_captions = lambda job: {
            "facebook": "templated caption",
            "telegram": "templated caption",
        }
        pipeline.create_current_job = lambda job: {
            **job,
            "job_id": "synthetic-job",
            "status": "pending",
        }
        pipeline.generate_ai_editorial = lambda facts: (
            AIEditorialDraft(
                headline="AI headline",
                caption="AI caption",
                generation_mode="ai_assisted",
                provider="synthetic-provider",
                model="synthetic-model",
                memory_references=("memory-1",),
            ),
            {
                "generation_mode": "ai_assisted",
                "provider": "synthetic-provider",
                "model": "synthetic-model",
                "fallback_level": 0,
                "validation_state": "valid",
                "memory_references": ["memory-1"],
                "rules_version": "test-1",
            },
        )
        job = pipeline.run_weather_pipeline(_base_job("ai_assisted"))
        assert job["editorial_mode"] == "ai_assisted"
        assert job["headline"] == "AI headline"
        assert job["captions"]["facebook"] == "AI caption"
        assert job["ai_provider"] == "synthetic-provider"
        assert job["ai_fallback_level"] == 0
        assert job["editorial_provenance"]["rules_version"] == "test-1"

        pipeline.generate_ai_editorial = lambda facts: (_ for _ in ()).throw(
            RuntimeError("provider chain unavailable")
        )
        automatic = pipeline.run_weather_pipeline(_base_job("automatic"))
        assert automatic["editorial_mode"] == "templated"
        assert automatic["ai_status"] == "fallback/degraded"
        assert automatic["headline"] != "AI headline"
        assert automatic["captions"]["facebook"] == "templated caption"

        try:
            pipeline.run_weather_pipeline(_base_job("ai_assisted"))
        except RuntimeError as error:
            assert "AI ASSISTED unavailable/degraded" in str(error)
            assert "TEMPLATED remains available" in str(error)
        else:
            raise AssertionError("Explicit ai_assisted failure must not produce TEMPLATED output")
    finally:
        pipeline.run_capture_job = original["capture"]
        pipeline.run_image_job = original["image"]
        pipeline.run_telegram_job = original["telegram"]
        pipeline.determine_map_framing = original["framing"]
        pipeline.build_captions = original["captions"]
        pipeline.create_current_job = original["store"]
        pipeline.generate_ai_editorial = original["generate"]
    print("editorial pipeline wiring verification ok")


if __name__ == "__main__":
    main()
