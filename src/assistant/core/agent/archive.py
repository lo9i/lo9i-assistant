import asyncio
import logging
from datetime import UTC, datetime

from assistant.core.agent.locking import LockingMixin
from assistant.core.conversation.epochs import archive

logger = logging.getLogger(__name__)


class ArchiveMixin(LockingMixin):
    """Turns a conversation that is being left into an episode and memory updates."""

    def _archive_in_background(self, thread_id: str, user_id: str) -> None:
        task = asyncio.create_task(self._archive(thread_id, user_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _archive(self, thread_id: str, user_id: str) -> None:
        try:
            async with self._thread_lock(thread_id):
                state = (await self._graph.aget_state({"configurable": {"thread_id": thread_id}})).values
                if await archive(state, self._storage.store, user_id, self._digester, datetime.now(UTC)):
                    logger.info("Archived conversation %s as an episode", thread_id)
        except Exception:
            logger.exception("Couldn't archive conversation %s", thread_id)
