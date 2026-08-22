"""Canonical writable-path boundary for local and managed runtimes."""

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath


RUNTIME_ROOT_ENV = "WEATHERWATCH_RUNTIME_ROOT"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_runtime_root():
    value = os.getenv(RUNTIME_ROOT_ENV)
    if not value or not value.strip():
        return None
    root = Path(value.strip()).expanduser()
    if not root.is_absolute():
        raise ValueError(f"{RUNTIME_ROOT_ENV} must be an absolute path.")
    return root.resolve()


def runtime_path(relative_path):
    """Resolve a repository-relative writable path under the optional root."""

    text = str(relative_path).replace("\\", "/")
    relative = PurePosixPath(text)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("Runtime paths must be non-empty repository-relative paths.")
    local_path = Path(*relative.parts)
    root = get_runtime_root()
    return root / local_path if root else local_path


def runtime_config_path(relative_path):
    """Resolve mutable configuration and seed a managed-runtime copy once.

    Local development keeps using the repository file. When a runtime root is
    configured, the checked-in file is copied to that root only when the
    operator-managed copy does not yet exist. Subsequent deploys therefore do
    not overwrite runtime edits.
    """

    destination = runtime_path(relative_path)
    root = get_runtime_root()
    if root is None or destination.exists():
        return destination

    source = (PROJECT_ROOT / Path(str(relative_path))).resolve()
    if not source.is_relative_to(PROJECT_ROOT) or not source.is_file():
        raise ValueError("Runtime configuration seed must be a repository file.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        shutil.copyfile(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    return destination
