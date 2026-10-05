"""Skills pinned to a conversation, for clients: list, pin and unpin them (core/conversation/pinned.py)."""

import asyncio

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import pinned
from assistant.core.skills import store


class PinnedSkillsMixin(ServiceBase):
    async def pinned_skills(self, user_id: str, thread_id: str) -> list[str]:
        return await pinned.load(self._storage.store, user_id, thread_id)

    async def pin_skill(self, user_id: str, thread_id: str, name: str) -> list[str]:
        """Takes effect at the next user message. Raises SkillError for an unknown skill."""
        await asyncio.to_thread(store.load, name)
        return await pinned.pin(self._storage.store, user_id, thread_id, name)

    async def unpin_skill(self, user_id: str, thread_id: str, name: str) -> list[str]:
        """Works for a skill deleted while pinned too."""
        return await pinned.unpin(self._storage.store, user_id, thread_id, name)
