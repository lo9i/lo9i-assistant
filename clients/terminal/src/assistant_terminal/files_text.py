"""Uploaded files as text, for the /files screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import UploadedFile
from assistant.core.config import settings


def describe(file: UploadedFile) -> str:
    """Markdown: the file, its type and size, when it was sent and in which conversation."""
    return (
        f"### {file.name}\n\n"
        f"{file.media_type}, {size(file.size)}\n\n"
        f"Sent {_local(file.uploaded_at)} in {file.conversation or 'an untitled conversation'}"
    )


def size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


def _local(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)).strftime("%a %d %b %H:%M")
