"""A file of the handed folder as the panel previews it: its text, up to MAX_BYTES, or none for a file that isn't
text. It's sent as text, never served as a file, so nothing in it runs in the app's page."""

import asyncio
import codecs
import os
from dataclasses import dataclass
from pathlib import Path

from assistant.core.handed_folder import paths
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError

MAX_BYTES = 256 * 1024
# A NUL byte in the start of a file says it isn't text.
_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class FilePreview:
    # Relative to the handed folder.
    path: str
    # In bytes, the whole file.
    size: int
    # None for a file that isn't text (a NUL byte, or not UTF-8).
    text: str | None
    # Bigger than MAX_BYTES: `text` is its start.
    truncated: bool


async def preview(root: Path, path: str) -> FilePreview:
    """Raises OutsideFolderError for a path outside `root` or one the panel doesn't show, MissingPathError for one
    that isn't a file there, HandedFolderError for one that can't be read."""
    where = paths.normal(path)
    target = await paths.shown(root, where)
    size, data = await asyncio.to_thread(_read, target, where)
    truncated = size > MAX_BYTES
    return FilePreview(where, size, as_text(data, whole=not truncated), truncated)


def as_text(data: bytes, whole: bool = True) -> str | None:
    """`data` as UTF-8 text, None when it isn't. Not `whole`, a character cut at its end is left out."""
    if b"\0" in data[:_SNIFF_BYTES]:
        return None
    try:
        return codecs.getincrementaldecoder("utf-8")().decode(data, final=whole)
    except UnicodeDecodeError:
        return None


def _read(target: Path, path: str) -> tuple[int, bytes]:
    if not target.is_file():
        raise MissingPathError(f"{path} isn't a file.")
    try:
        with target.open("rb") as f:
            return os.fstat(f.fileno()).st_size, f.read(MAX_BYTES)
    except OSError as e:
        raise HandedFolderError(f"Can't read {path}: {e.strerror or e}") from e
