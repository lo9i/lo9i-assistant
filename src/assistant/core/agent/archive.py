import asyncio
import logging
from datetime import UTC, datetime

from assistant.core import conversations
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.titles import TitlesMixin
from assistant.core.conversation.epochs import archive

logger = logging.getLogger(__name__)


class ArchiveMixin(LockingMixin, TitlesMixin):
    """Turns a conversation that is being left into an episode and memory updates."""

    def _archive_in_background(self, thread_id: str, user_id: str) -> None:
        task = asyncio.create_task(self._archive(thread_id, user_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _archive(self, thread_id: str, user_id: str) -> None:
        try:
            async with self._thread_lock(thread_id):
                await self._archive_locked(thread_id, user_id)
        except Exception:
            logger.exception("Couldn't archive conversation %s", thread_id)

    async def _archive_locked(self, thread_id: str, user_id: str) -> None:
        """Archives only what came after the last archive, so a conversation resumed and left
        again doesn't repeat an episode."""
        store = self._storage.store
        state = (await self._graph.aget_state({"configurable": {"thread_id": thread_id}})).values
        record = await conversations.load(store, user_id, thread_id)
        after = record.archived_upto if record else 0
        if not await archive(state, store, user_id, self._digester, datetime.now(UTC), after):
            return
        logger.info("Archived conversation %s as an episode", thread_id)
        async with self._conversations_lock:
            await conversations.mark_archived(store, user_id, thread_id, len(state.get("messages", [])))
        await self._retitle(user_id, thread_id, state.get("messages", []))
