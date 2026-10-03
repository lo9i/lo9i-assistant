"""The files the user sent in their conversations, read from the messages that refer to them."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from assistant.core import conversations, uploads
from assistant.core.agent.base import ServiceBase
from assistant.core.attachments import user_uploads
from assistant.core.conversations import Conversation

__all__ = ["FilesMixin", "UploadedFile"]


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


class FilesMixin(ServiceBase):
    async def list_files(self, user_id: str) -> list[UploadedFile]:
        """Newest first. Files no longer on disk are left out."""
        found: list[UploadedFile] = []
        for conversation in await conversations.recent(self._storage.store, user_id):
            state = await self._graph.aget_state({"configurable": {"thread_id": conversation.thread_id}})
            references = user_uploads(state.values.get("messages", []))
            found += await asyncio.to_thread(_on_disk, conversation, references)
        return sorted(found, key=lambda f: f.uploaded_at, reverse=True)


def _on_disk(conversation: Conversation, references: list[dict[str, str]]) -> list[UploadedFile]:
    return [f for r in references if (f := _file(conversation, r)) is not None]


def _file(conversation: Conversation, reference: dict[str, str]) -> UploadedFile | None:
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
    )
