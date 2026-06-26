from datetime import datetime, timedelta
from pathlib import Path

from storage.approval_store import get_current_job


MANUAL_INPUTS_DIR = Path("output/manual_inputs")
MANUAL_INPUT_RETENTION_DAYS = 7


def protected_current_job_paths():
    current = get_current_job() or {}
    paths = set()

    for key in ("raw_image", "image"):
        value = current.get(key)

        if value:
            paths.add(Path(value).resolve())

    return paths


def cleanup_manual_inputs(retention_days=MANUAL_INPUT_RETENTION_DAYS):
    if not MANUAL_INPUTS_DIR.exists():
        return []

    cutoff = datetime.now() - timedelta(days=retention_days)
    protected_paths = protected_current_job_paths()
    deleted = []

    for path in MANUAL_INPUTS_DIR.iterdir():
        if not path.is_file():
            continue

        resolved_path = path.resolve()

        if resolved_path in protected_paths:
            continue

        modified_at = datetime.fromtimestamp(path.stat().st_mtime)

        if modified_at >= cutoff:
            continue

        path.unlink()
        deleted.append(str(path))

    return deleted
