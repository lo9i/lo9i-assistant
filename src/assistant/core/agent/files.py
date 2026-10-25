"""The files in the user's conversations, read from the messages that refer to them: the ones the user sent
and the ones tool results brought (an email's attachments, an MCP tool's images)."""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage

from assistant.core import conversations, uploads
from assistant.core.agent.thread_files import ThreadFilesMixin
from assistant.core.agent_tasks import sent
from assistant.core.attachments import tool_uploads, user_uploads
from assistant.core.conversations import Conversation

__all__ = ["FileUnavailableError", "FilesMixin", "UploadedFile"]

_MCP_TOOL = re.compile(r"mcp__(.+?)__(.+)")


@dataclass
class UploadedFile:
    # Relative to the uploads dir.
    path: str
    name: str
    media_type: str
    size: int
    uploaded_at: str
    thread_id: str
    conversation: str
    # The tool whose result brought it (read_email, mcp__<server>__<tool>); "" for a file the user sent.
    tool: str


class FileUnavailableError(Exception):
    """No file in the user's conversations has that path (deleted with its conversation, or never one of theirs)."""


class FilesMixin(ThreadFilesMixin):
    async def list_files(self, user_id: str) -> list[UploadedFile]:
        """Newest first, each file once. Files no longer on disk are left out."""
        found: list[UploadedFile] = []
        for conversation in await conversations.recent(self._storage.store, user_id):
            references = _references(await self._thread_messages(conversation.thread_id))
            found += await asyncio.to_thread(_on_disk, conversation, references)
        return sorted(_once(found), key=lambda f: (f.uploaded_at, f.path), reverse=True)

    async def files_page(
        self, user_id: str, query: str = "", offset: int = 0, limit: int | None = None
    ) -> list[UploadedFile]:
        """The files matching `query` (by name, type, where they came from or conversation), newest first, from
        `offset`: at most `limit`, all of them with None. Each page still reads every conversation (BACKLOG.md)."""
        words = query.strip().lower()
        matching = [f for f in await self.list_files(user_id) if words in _searched(f)]
        return matching[offset : None if limit is None else offset + limit]

    async def file_content(self, user_id: str, path: str) -> tuple[UploadedFile, bytes]:
        """A file from the list, to view or download. Only paths the list has, so nothing else in the
        uploads folder can be read through it. Raises FileUnavailableError."""
        file = next((f for f in await self.list_files(user_id) if f.path == path), None)
        data = await asyncio.to_thread(uploads.load, path) if file else None
        if file is None or data is None:
            raise FileUnavailableError("That file isn't there any more.")
        return file, data


def _references(messages: Sequence[BaseMessage]) -> list[tuple[str, dict[str, str]]]:
    """Each file's reference with the tool that brought it, "" for the user's (to an agent at work too)."""
    return [("", r) for r in [*user_uploads(messages), *sent.uploads(messages)]] + tool_uploads(messages)


def _searched(file: UploadedFile) -> str:
    """What a search looks in, as the Files page shows it: the user, or the tool (an MCP tool as "server: tool")."""
    mcp = _MCP_TOOL.match(file.tool)
    source = f"{mcp[1]}: {mcp[2]}" if mcp else file.tool or "You"
    return f"{file.name} {file.media_type} {source} {file.conversation}".lower()


def _once(files: list[UploadedFile]) -> list[UploadedFile]:
    """One entry per file, with the conversation written in last: a file can be in several (a message the inbox
    sent on keeps its files in the inbox and where it went), and the apps list each file by its path."""
    return list({f.path: f for f in reversed(files)}.values())


def _on_disk(conversation: Conversation, references: list[tuple[str, dict[str, str]]]) -> list[UploadedFile]:
    return [f for tool, r in references if (f := _file(conversation, tool, r)) is not None]


def _file(conversation: Conversation, tool: str, reference: dict[str, str]) -> UploadedFile | None:
    path = uploads.absolute(reference["path"])
    if not path.is_file():
        return None
    stat = path.stat()
    return UploadedFile(
        path=reference["path"],
        name=reference["name"],
        media_type=reference["media_type"],
        size=stat.st_size,
        uploaded_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        thread_id=conversation.thread_id,
        conversation=conversation.title,
        tool=tool,
    )
