"""Small filesystem-backed state boundary for durable runtime state.

The repository keeps the current runtime compatible with JSON files while
isolating atomic persistence and safe reads so a future durable backend can
replace this boundary without changing approval-domain code.
"""

import json
import os
import tempfile
import time
from pathlib import Path


class JsonStateRepository:
    def __init__(self, path, *, read_attempts=3, retry_seconds=0.02):
        self.path = Path(path)
        self.read_attempts = read_attempts
        self.retry_seconds = retry_seconds

    def load(self, default_factory):
        if not self.path.exists():
            return default_factory()

        last_error = None
        for attempt in range(self.read_attempts):
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                if not self.path.exists():
                    return default_factory()
                last_error = FileNotFoundError("State file temporarily unavailable.")
            except json.JSONDecodeError as error:
                last_error = error

            if attempt < self.read_attempts - 1:
                time.sleep(self.retry_seconds)

        raise RuntimeError(
            "State could not be read safely. The existing state file was not replaced."
        ) from last_error

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(state, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())

            os.replace(temporary_path, self.path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()

