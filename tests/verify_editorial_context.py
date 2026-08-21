import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.editorial_context_service import build_editorial_context
from services.editorial_memory_service import load_editorial_memory


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        memory_path = root / "memory.json"
        memory_path.write_text(json.dumps([
            {
                "memory_id": "rain-1",
                "headline": "Rain headline",
                "caption": "Rain caption",
                "tags": ["rain", "cagayan"],
                "approved": True,
                "category": "rain_advisory",
            },
            {
                "memory_id": "rejected-1",
                "headline": "Rejected",
                "caption": "Rejected",
                "tags": ["rain"],
                "approved": False,
            },
        ]), encoding="utf-8")
        rules_path = root / "rules.json"
        rules_path.write_text(json.dumps({
            "version": "test-1",
            "rules": ["Do not invent weather facts."],
            "output_schema": {"headline": "string", "caption": "string"},
        }), encoding="utf-8")
        context = build_editorial_context(
            {"affected_weather_system": "rain", "wind_kmh": 20},
            memory_tags=["rain", "cagayan"],
            memory_path=memory_path,
            rules_path=rules_path,
            memory_limit=1,
        )
        assert context["weather_facts"]["wind_kmh"] == 20
        assert context["rules_version"] == "test-1"
        assert context["memory_references"] == ["rain-1"]
        assert len(context["memory_examples"]) == 1
        assert "rejected-1" not in json.dumps(context)
        assert "Do not invent weather facts." in context["editorial_rules"]

        malformed = root / "malformed.json"
        malformed.write_text("{}", encoding="utf-8")
        try:
            load_editorial_memory(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed memory corpus must fail closed")
    print("editorial context verification ok")


if __name__ == "__main__":
    main()
