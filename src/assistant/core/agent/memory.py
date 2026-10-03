import asyncio

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.config import settings
from assistant.core.memory import episodes, facts, profile
from assistant.core.skills import store as skills


class MemoryMixin(ServiceBase):
    """Read-only view of the user's long-term memory."""

    async def memory_snapshot(self, user_id: str) -> MemorySnapshot:
        store = self._storage.store
        current = await profile.load(store, user_id)
        return MemorySnapshot(
            profile={name: items for name, items in current.model_dump().items() if items},
            facts=[f.text for f in await facts.load(store, user_id, settings.memory_max_facts)],
            episodes=[e.summary for e in await episodes.recent(store, user_id, settings.memory_max_episodes)],
            skills=[s.name for s in await asyncio.to_thread(skills.saved_skills)],
        )
