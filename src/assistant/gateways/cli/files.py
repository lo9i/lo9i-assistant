"""Reads a local file into an Attachment for the CLI's /attach command."""

import mimetypes
from pathlib import Path

from assistant.core.attachments import Attachment


def load_attachment(raw_path: str) -> Attachment:
    """Raises FileNotFoundError when the path isn't a file."""
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Attachment(name=path.name, media_type=media_type, data=path.read_bytes())
