import logging

from assistant.core.agent.conversations import ConversationsMixin

logger = logging.getLogger(__name__)


class SearchMixin(ConversationsMixin):
    """Keeps the message search index (core/conversation/search.py) in step with conversations."""

    async def index_messages(self, user_id: str) -> int:
        """Indexes the messages of conversations saved before search existed, or whose last run
        wasn't indexed. Returns how many messages were added."""
        added = 0
        for thread_id in await self._saved_threads(user_id):
            added += await self._index_thread(user_id, thread_id)
        return added

    async def conversations_containing(self, user_id: str, text: str) -> list[str]:
        """The ids of the conversations whose messages hold every word of `text`, each as a word's start."""
        return await self._storage.search.threads_with(user_id, text)

    async def _index_after_run(self, user_id: str, thread_id: str) -> None:
        """A failure leaves the conversation as it is; its messages are indexed after its next run."""
        try:
            await self._index_thread(user_id, thread_id)
        except Exception:
            logger.exception("Couldn't index the messages of conversation %s", thread_id)

    async def _index_thread(self, user_id: str, thread_id: str) -> int:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        return await self._storage.search.add(user_id, thread_id, state.values.get("messages", []))
