"""The files a conversation's messages refer to: the uploads the user sent and tool results brought, those
sent to an agent while it worked (core/agent_tasks/sent.py), and the voice recordings. The Files list
(files.py) reads them, and deleting a conversation (threads.py) deletes them unless another conversation
refers to them too (a message the inbox sent on keeps its files in both)."""

from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from assistant.core import checkpoints, conversations, uploads
from assistant.core.agent.base import ServiceBase
from assistant.core.agent_tasks import sent
from assistant.core.attachments import upload_paths
from assistant.core.speech.voice import audio_paths


class ThreadFilesMixin(ServiceBase):
    async def _thread_messages(self, thread_id: str) -> list[BaseMessage]:
        """The conversation's messages, then those of the subagents its delegate calls ran, each kept under its
        call's namespace: their tools bring files too (an email's attachments)."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        messages = list(state.values.get("messages", []))
        for namespace in await checkpoints.subgraph_namespaces(self._storage.checkpointer, thread_id):
            messages += await self._subgraph_messages(thread_id, namespace)
        return messages

    async def _subgraph_messages(self, thread_id: str, namespace: str) -> list[BaseMessage]:
        config = RunnableConfig(configurable={"thread_id": thread_id, "checkpoint_ns": namespace})
        saved = await self._storage.checkpointer.aget_tuple(config)
        return list(saved.checkpoint["channel_values"].get("messages", [])) if saved else []

    async def _files_elsewhere(self, user_id: str, thread_id: str) -> list[Path]:
        """The files the user's conversations other than `thread_id` refer to."""
        found: list[Path] = []
        for conversation in await conversations.recent(self._storage.store, user_id):
            if conversation.thread_id != thread_id:
                found += referenced(await self._thread_messages(conversation.thread_id))
        return found


def referenced(messages: Sequence[BaseMessage]) -> list[Path]:
    """The files the messages refer to: uploads, those sent to an agent while it worked, and voice recordings."""
    paths = [*upload_paths(messages), *(upload["path"] for upload in sent.uploads(messages))]
    return [uploads.absolute(p) for p in paths] + audio_paths(messages)
