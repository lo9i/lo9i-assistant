"""Files in the conversations as text, for the /files screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import UploadedFile
from assistant.core.config import settings


def describe(file: UploadedFile) -> str:
    """Markdown: the file, its type and size, where it came from, when, and in which conversation."""
    came = f"From {source(file)}" if file.tool else "Sent"
    return (
        f"### {file.name}\n\n"
        f"{file.media_type}, {size(file.size)}\n\n"
        f"{came} {_local(file.uploaded_at)} in {file.conversation or 'an untitled conversation'}"
    )


def source(file: UploadedFile) -> str:
    """The user, or the tool whose result brought it (an MCP tool as "server: tool")."""
    server, _, tool = file.tool.removeprefix("mcp__").partition("__")
    if file.tool.startswith("mcp__") and tool:
        return f"{server}: {tool}"
    return file.tool or "you"


def size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


def _local(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)).strftime("%a %d %b %H:%M")
