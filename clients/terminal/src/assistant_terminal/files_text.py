"""Files in the conversations as text, for the /files screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import UploadedFile
from assistant.core.config import settings
from assistant_terminal.i18n import decimal, short_date, t


def describe(file: UploadedFile) -> str:
    """Markdown: the file, its type and size, where it came from, when, and in which conversation."""
    where = file.conversation or t("an untitled conversation")
    came = (
        t(
            "From {source} {when} in {conversation}",
            source=source(file),
            when=_local(file.uploaded_at),
            conversation=where,
        )
        if file.tool
        else t("Sent {when} in {conversation}", when=_local(file.uploaded_at), conversation=where)
    )
    return f"### {file.name}\n\n{file.media_type}, {size(file.size)}\n\n{came}"


def source(file: UploadedFile) -> str:
    """The user, or the tool whose result brought it (an MCP tool as "server: tool")."""
    server, _, tool = file.tool.removeprefix("mcp__").partition("__")
    if file.tool.startswith("mcp__") and tool:
        return f"{server}: {tool}"
    return file.tool or t("you")


def size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{decimal(count / 1024)} KB"
    return f"{decimal(count / (1024 * 1024))} MB"


def _local(timestamp: str) -> str:
    return short_date(datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)))
