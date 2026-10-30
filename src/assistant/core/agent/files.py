"""The files in the user's conversations, read from the index of the messages that refer to them
(core/conversation/file_index.py): the ones the user sent and the ones tool results brought (an email's attachments,
an MCP tool's images)."""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from assistant.core import conversations, uploads
from assistant.core.agent.thread_files import ThreadFilesMixin
from assistant.core.conversation import file_index
from assistant.core.conversation.file_index import FileReference
from assistant.core.conversations import Conversation
from assistant.core.i18n import said

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
        indexed = await file_index.of_user(self._storage.store, user_id)
        found: list[tuple[Conversation, list[FileReference]]] = []
        for conversation in await conversations.recent(self._storage.store, user_id):
            found.append((conversation, await self._references(conversation.thread_id, indexed)))
        files = await asyncio.to_thread(_on_disk, found)
        return sorted(_once(files), key=lambda f: (f.uploaded_at, f.path), reverse=True)

    async def _references(self, thread_id: str, indexed: dict[str, list[FileReference]]) -> list[FileReference]:
        """From the index, but for a conversation with a run in progress, whose files are indexed when it ends, or
        one not indexed yet: from its messages."""
        if thread_id in indexed and thread_id not in self._run_starts:
            return indexed[thread_id]
        return file_index.references(await self._thread_messages(thread_id))

    async def files_page(
        self, user_id: str, query: str = "", offset: int = 0, limit: int | None = None
    ) -> list[UploadedFile]:
        """The files matching `query` (by name, type, where they came from or conversation), newest first, from
        `offset`: at most `limit`, all of them with None."""
        words = query.strip().lower()
        matching = [f for f in await self.list_files(user_id) if words in _searched(f)]
        return matching[offset : None if limit is None else offset + limit]

    async def file_content(self, user_id: str, path: str) -> tuple[UploadedFile, bytes]:
        """A file from the list, to view or download. Only paths the list has, so nothing else in the
        uploads folder can be read through it. Raises FileUnavailableError."""
        file = next((f for f in await self.list_files(user_id) if f.path == path), None)
        data = await asyncio.to_thread(uploads.load, path) if file else None
        if file is None or data is None:
            raise FileUnavailableError(said("That file isn't there any more."))
        return file, data


def _searched(file: UploadedFile) -> str:
    """What a search looks in, as the Files page shows it: the user, or the tool (an MCP tool as "server: tool")."""
    mcp = _MCP_TOOL.match(file.tool)
    source = f"{mcp[1]}: {mcp[2]}" if mcp else file.tool or "You"
    return f"{file.name} {file.media_type} {source} {file.conversation}".lower()


def _once(files: list[UploadedFile]) -> list[UploadedFile]:
    """One entry per file, with the conversation written in last: a file can be in several (a message the inbox
    sent on keeps its files in the inbox and where it went), and the apps list each file by its path."""
    return list({f.path: f for f in reversed(files)}.values())


def _on_disk(found: list[tuple[Conversation, list[FileReference]]]) -> list[UploadedFile]:
    return [f for conversation, references in found for r in references if (f := _file(conversation, r))]


def _file(conversation: Conversation, reference: FileReference) -> UploadedFile | None:
    path = uploads.absolute(reference.path)
    if not path.is_file():
        return None
    stat = path.stat()
    return UploadedFile(
        path=reference.path,
        name=reference.name,
        media_type=reference.media_type,
        size=stat.st_size,
        uploaded_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        thread_id=conversation.thread_id,
        conversation=conversation.title,
        tool=reference.tool,
    )
