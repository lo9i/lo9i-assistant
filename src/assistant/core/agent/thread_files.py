"""The files a conversation's messages refer to: the uploads the user sent and tool results brought, those
sent to an agent while it worked (core/agent_tasks/sent.py), and the voice recordings. The Files list
(files.py) reads them from their index (core/conversation/file_index.py), kept here, and deleting a conversation
(threads.py) deletes them unless another conversation refers to them too (a message the inbox sent on keeps its
files in both)."""

import logging
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from assistant.core import checkpoints, conversations, uploads
from assistant.core.agent.base import ServiceBase
from assistant.core.agent_tasks import sent
from assistant.core.attachments import upload_paths
from assistant.core.conversation import file_index
from assistant.core.speech.voice import audio_paths

logger = logging.getLogger(__name__)


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

    async def fill_file_index(self, user_id: str) -> int:
        """Indexes the files of conversations listed before the index was kept, each read once. Returns how many
        were indexed."""
        indexed = await file_index.of_user(self._storage.store, user_id)
        listed = await conversations.recent(self._storage.store, user_id)
        missing = [c.thread_id for c in listed if c.thread_id not in indexed]
        for thread_id in missing:
            await self._index_files(user_id, thread_id)
        return len(missing)

    async def _index_files_after_run(self, user_id: str, thread_id: str) -> None:
        """A failure leaves the index as it was, without what this run brought, until a later run's is indexed."""
        try:
            await self._index_files(user_id, thread_id)
        except Exception:
            logger.exception("Couldn't index the files of conversation %s", thread_id)

    async def _index_files(self, user_id: str, thread_id: str) -> None:
        references = file_index.references(await self._thread_messages(thread_id))
        await file_index.save(self._storage.store, user_id, thread_id, references)

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
