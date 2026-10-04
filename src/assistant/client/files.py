"""Reads a local file into an Attachment, for clients that attach files by path (the CLI's /attach,
or files dropped on a terminal window, which pastes their paths)."""

import mimetypes
import shlex
from pathlib import Path
from urllib.parse import unquote, urlparse

from assistant.core.attachments import Attachment


def load_attachment(raw_path: str) -> Attachment:
    """Raises FileNotFoundError when the path isn't a file."""
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Attachment(name=path.name, media_type=media_type, data=path.read_bytes())


def dropped_paths(text: str) -> list[Path]:
    """The files a paste names when it's only paths of existing files, as a terminal pastes them
    for files dropped on its window: escaped (`My\\ File.png`), quoted, or as file:// URLs, several
    separated by spaces. Empty for anything else, which is text to type."""
    try:
        words = shlex.split(text.strip())
    except ValueError:
        return []
    paths = [_path(word) for word in words]
    return paths if paths and all(p.is_file() for p in paths) else []


def _path(word: str) -> Path:
    if word.startswith("file://"):
        return Path(unquote(urlparse(word).path))
    return Path(word).expanduser()


def save_download(name: str, data: bytes, folder: Path | None = None) -> Path:
    """Saves a file from the daemon in the Downloads folder (`folder` for tests), under its name, or
    "name (2).ext" and so on when that's taken. Returns where it went."""
    target_folder = folder or Path.home() / "Downloads"
    target_folder.mkdir(parents=True, exist_ok=True)
    safe = Path(name).name or "file"
    target, number = target_folder / safe, 2
    while target.exists():
        target, number = target_folder / f"{Path(safe).stem} ({number}){Path(safe).suffix}", number + 1
    target.write_bytes(data)
    return target
