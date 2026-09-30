"""Skills for clients: list, read and delete them."""

import asyncio
from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.skills import store
from assistant.core.skills.store import Skill, SkillError

__all__ = ["Skill", "SkillError", "SkillSummary", "SkillsMixin"]


@dataclass
class SkillSummary:
    name: str
    description: str


class SkillsMixin(ServiceBase):
    async def list_skills(self) -> list[SkillSummary]:
        return [SkillSummary(s.name, s.description) for s in await asyncio.to_thread(store.list_skills)]

    async def get_skill(self, name: str) -> Skill:
        """Raises SkillError if it doesn't exist."""
        return await asyncio.to_thread(store.load, name)

    async def delete_skill(self, name: str) -> None:
        await asyncio.to_thread(store.delete, name)
        self.bus.publish("skills")
