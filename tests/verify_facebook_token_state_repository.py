import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage.facebook_token_store as token_store


def main():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_file = token_store.STATE_FILE
    temporary_directory = tempfile.TemporaryDirectory()
    try:
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "filesystem"
        token_store.STATE_FILE = Path(temporary_directory.name) / "token-state.json"
        saved = token_store.save_page_token(
            "page-1", "Synthetic Page", "synthetic-token"
        )
        assert token_store.load_facebook_token_state()["page_id"] == "page-1"
        assert "access_token" not in token_store.public_token_state(saved)
        assert "synthetic-token" not in str(token_store.public_token_state(saved))
    finally:
        token_store.STATE_FILE = original_file
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        temporary_directory.cleanup()
    print("facebook token state repository verification ok")


if __name__ == "__main__":
    main()
