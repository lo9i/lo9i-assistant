"""Stores uploaded files on disk under `settings.uploads_dir`. Paths are relative to that dir."""

from pathlib import Path
from uuid import uuid4

from assistant.core.config import settings


def save(name: str, data: bytes) -> str:
    """Write the file and return its path relative to the uploads dir."""
    relative = f"{uuid4().hex}/{Path(name).name}"
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
