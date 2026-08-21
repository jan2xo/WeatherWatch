import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    root = Path(__file__).resolve().parents[1]
    document = (root / "docs/DEPLOYMENT_VERIFICATION.md").read_text(encoding="utf-8")
    assert "application_alive" in document
    assert "owner-controlled" in document
    assert "ephemeral filesystem" in document
    assert "production secrets" in document
    assert "P12 remains BLOCKED" in document
    assert (root / "docs/VPS_DEPLOYMENT.md").is_file()
    assert (root / "scripts/verify_install.sh").is_file()
    print("deployment boundary verification ok")


if __name__ == "__main__":
    main()
