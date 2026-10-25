"""Stores uploaded files on disk under `settings.uploads_dir`. Paths are relative to that dir."""

from pathlib import Path
from uuid import uuid4

from assistant.core.config import settings


def save(name: str, data: bytes, folder: str = "") -> str:
    """Write the file, optionally under a subfolder, and return its path relative to the uploads dir."""
    relative = str(Path(folder) / uuid4().hex / Path(name).name)
    target = absolute(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative


def load(relative: str) -> bytes | None:
    """File contents, or None if the file was deleted."""
    path = absolute(relative)
    return path.read_bytes() if path.is_file() else None


def absolute(relative: str) -> Path:
    return Path(settings.uploads_dir).expanduser() / relative


def delete(relative: str) -> None:
    """Removes the file, and the folder `save` made for it once it's empty."""
    path = absolute(relative)
    path.unlink(missing_ok=True)
    if path.parent != absolute("") and path.parent.is_dir() and not any(path.parent.iterdir()):
        path.parent.rmdir()
