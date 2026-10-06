import asyncio

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.config import settings
from assistant.core.memory import episodes, facts, profile
from assistant.core.memory.episodes import Episode
from assistant.core.memory.facts import Fact
from assistant.core.memory.profile import Section
from assistant.core.skills import store as skills

__all__ = ["Episode", "Fact", "MemoryEditError", "MemoryMixin", "MemoryNotFoundError"]


class MemoryEditError(Exception):
    pass


class MemoryNotFoundError(MemoryEditError):
    """The fact or episode was deleted, by the user or by the assistant."""


class MemoryMixin(ServiceBase):
    """The user's long-term memory: shown to the apps, and edited there too. Like the assistant's own
    changes, edits reach the system prompt from the next epoch."""

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

    async def saved_facts(self, user_id: str) -> list[Fact]:
        """Every saved fact, newest first: the system prompt holds the latest ones, search_memory finds the rest."""
        return sorted(await facts.load_all(self._storage.store, user_id), key=lambda f: f.saved_at, reverse=True)

    async def edit_fact(self, user_id: str, fact_id: str, text: str) -> Fact:
        """It gets a new id. Raises MemoryNotFoundError for one that's gone, MemoryEditError for empty text."""
        edited = await facts.replace(self._storage.store, user_id, fact_id, _text(text))
        if edited is None:
            raise MemoryNotFoundError(f"There's no saved fact {fact_id} any more.")
        return edited

    async def delete_fact(self, user_id: str, fact_id: str) -> None:
        if not await facts.get(self._storage.store, user_id, [fact_id]):
            raise MemoryNotFoundError(f"There's no saved fact {fact_id} any more.")
        await facts.remove(self._storage.store, user_id, fact_id)

    async def saved_episodes(self, user_id: str) -> list[Episode]:
        """Every summary of a past conversation, newest first."""
        return sorted(await episodes.load_all(self._storage.store, user_id), key=lambda e: e.ended_at, reverse=True)

    async def edit_episode(self, user_id: str, episode_id: str, summary: str) -> Episode:
        """It gets a new id. Raises MemoryNotFoundError for one that's gone, MemoryEditError for empty text."""
        edited = await episodes.replace(self._storage.store, user_id, episode_id, _text(summary))
        if edited is None:
            raise MemoryNotFoundError(f"There's no conversation summary {episode_id} any more.")
        return edited

    async def delete_episode(self, user_id: str, episode_id: str) -> None:
        if not await episodes.get(self._storage.store, user_id, [episode_id]):
            raise MemoryNotFoundError(f"There's no conversation summary {episode_id} any more.")
        await episodes.remove(self._storage.store, user_id, episode_id)


def _text(text: str) -> str:
    if not text.strip():
        raise MemoryEditError("Write something, or delete it instead.")
    return text.strip()
