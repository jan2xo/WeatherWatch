import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    root = Path(__file__).resolve().parents[1]
    document = (root / "docs/DEPLOYMENT_VERIFICATION.md").read_text(encoding="utf-8")
    assert "application_alive" in document
    assert "owner-controlled" in document
    assert "Repository implementation: complete candidate" in document
    assert "Render service creation/configuration: pending" in document
    assert "Render Chromium/WINDY live certification: pending" in document
    assert "Production Redis wiring/recovery: pending" in document
    assert "Actual AI provider/model/key configuration: pending" in document
    assert "Real editorial memory population: pending" in document
    assert "Live Telegram verification: pending" in document
    assert "Live Facebook verification: pending" in document
    assert "Restart/recovery certification: pending" in document
    assert "Production certification: pending" in document
    assert "does not call Render" in document
    assert (root / "docs/VPS_DEPLOYMENT.md").is_file()
    assert (root / "scripts/verify_install.sh").is_file()
    print("deployment boundary verification ok")


if __name__ == "__main__":
    main()
