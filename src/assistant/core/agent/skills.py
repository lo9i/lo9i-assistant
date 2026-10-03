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
        """The saved skills. Built-in ones (assistant-setup) aren't listed: the assistant uses them,
        the user doesn't manage them."""
        return [SkillSummary(s.name, s.description) for s in await asyncio.to_thread(store.saved_skills)]

    async def get_skill(self, name: str) -> Skill:
        """Raises SkillError if it doesn't exist."""
        return await asyncio.to_thread(store.load, name)

    async def update_skill(self, name: str, description: str, instructions: str) -> Skill:
        """Change a saved skill. Raises SkillError for an unknown or built-in skill, or empty text."""
        await self.get_skill(name)
        if not description.strip() or not instructions.strip():
            raise SkillError("A skill needs a description and instructions.")
        skill = await asyncio.to_thread(store.save, name, description, instructions)
        self.bus.publish("skills")
        return skill

    async def delete_skill(self, name: str) -> None:
        await asyncio.to_thread(store.delete, name)
        self.bus.publish("skills")
