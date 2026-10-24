"""The files a conversation's messages refer to: the uploads the user sent and tool results brought, and the
voice recordings. The Files list (files.py) reads them, and deleting a conversation (threads.py) deletes them
unless another conversation refers to them too (a message the inbox sent on keeps its files in both)."""

from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import BaseMessage

from assistant.core import conversations, uploads
from assistant.core.agent.base import ServiceBase
from assistant.core.attachments import upload_paths
from assistant.core.speech.voice import audio_paths


class ThreadFilesMixin(ServiceBase):
    async def _thread_messages(self, thread_id: str) -> list[BaseMessage]:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        return list(state.values.get("messages", []))

    async def _files_elsewhere(self, user_id: str, thread_id: str) -> list[Path]:
        """The files the user's conversations other than `thread_id` refer to."""
        found: list[Path] = []
        for conversation in await conversations.recent(self._storage.store, user_id):
            if conversation.thread_id != thread_id:
                found += referenced(await self._thread_messages(conversation.thread_id))
        return found


def referenced(messages: Sequence[BaseMessage]) -> list[Path]:
    """The files the messages refer to: uploads and voice recordings."""
    return [uploads.absolute(p) for p in upload_paths(messages)] + audio_paths(messages)
