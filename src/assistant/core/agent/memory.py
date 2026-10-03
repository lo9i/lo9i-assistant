import asyncio

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.config import settings
from assistant.core.memory import episodes, facts, profile
from assistant.core.memory.profile import Section
from assistant.core.skills import store as skills


class MemoryMixin(ServiceBase):
    """The user's long-term memory: shown to the apps, and the profile edited there too."""

    async def memory_snapshot(self, user_id: str) -> MemorySnapshot:
        store = self._storage.store
        current = await profile.load(store, user_id)
        return MemorySnapshot(
            profile={name: items for name, items in current.model_dump().items() if items},
            profile_sections=list(profile.Profile.model_fields),
            facts=[f.text for f in await facts.load(store, user_id, settings.memory_max_facts)],
            episodes=[e.summary for e in await episodes.recent(store, user_id, settings.memory_max_episodes)],
            skills=[s.name for s in await asyncio.to_thread(skills.saved_skills)],
        )

    async def set_profile_section(self, user_id: str, section: Section, items: list[str]) -> MemorySnapshot:
        """Replaces one profile section with what the user wrote in an app. Like the assistant's own
        changes, it reaches the system prompt from the next epoch."""
        store = self._storage.store
        current = await profile.load(store, user_id)
        cleaned = [item.strip() for item in items if item.strip()]
        await profile.save(store, user_id, profile.Profile.model_validate(current.model_dump() | {section: cleaned}))
        return await self.memory_snapshot(user_id)
