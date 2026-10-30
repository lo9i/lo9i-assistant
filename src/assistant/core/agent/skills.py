"""Skills for clients: list, read, edit and delete them, and update installed ones from their repository."""

import asyncio
from dataclasses import dataclass, field

from assistant.core.agent.base import ServiceBase
from assistant.core.health import Health
from assistant.core.i18n import said
from assistant.core.repositories import listed
from assistant.core.repositories.listed import KeptKeys
from assistant.core.skills import install, store
from assistant.core.skills.install import FoundSkill
from assistant.core.skills.store import Skill, SkillError

__all__ = ["FoundSkill", "Skill", "SkillError", "SkillSummary", "SkillsMixin"]


@dataclass
class SkillSummary:
    name: str
    description: str
    # What's wrong with it as written (core/skills/store.py::problems).
    problems: list[str] = field(default_factory=list)
    # Its scripts' failures in a row (core/health.py), and the last failure.
    failures: int = 0
    failure: str = ""
    failed_at: str = ""
    # At least FAILING_AFTER in a row: the user was alerted.
    failing: bool = False
    # The plugin that added it; "" when the user or the assistant wrote it here.
    plugin: str = ""


class SkillsMixin(ServiceBase):
    async def list_skills(self) -> list[SkillSummary]:
        """The saved skills. Built-in ones (assistant-setup) aren't listed: the assistant uses them,
        the user doesn't manage them."""
        health = await self._health.all("skill")
        return [_summary(s, health.get(s.name, Health())) for s in await asyncio.to_thread(store.saved_skills)]

    async def get_skill(self, name: str) -> Skill:
        """Raises SkillError if it doesn't exist."""
        return await asyncio.to_thread(store.load, name)

    async def update_skill(self, name: str, description: str, instructions: str) -> Skill:
        """Change a saved skill. Raises SkillError for an unknown or built-in skill, or empty text."""
        await self.get_skill(name)
        if not description.strip() or not instructions.strip():
            raise SkillError(said("A skill needs a description and instructions."))
        skill = await asyncio.to_thread(store.save, name, description, instructions)
        self.bus.publish("skills")
        return skill

    async def delete_skill(self, name: str) -> KeptKeys | None:
        """The token of the private repository it came from, when nothing else needs it any more, is
        returned for the user to keep or delete (forget_keys)."""
        source = await asyncio.to_thread(store.installed_from, name)
        await asyncio.to_thread(store.delete, name)
        await self._health.forget("skill", name)
        self.bus.publish("skills")
        return await listed.after_removal(self._storage.store, name, source.url) if source and source.url else None

    async def update_installed_skill(self, name: str) -> Skill:
        """Install the skill again from its repository. Raises SkillError if it wasn't installed."""
        skill = await install.update(name, await listed.tokens(self._storage.store, self.secrets))
        self.bus.publish("skills")
        return skill


def _summary(skill: Skill, health: Health) -> SkillSummary:
    return SkillSummary(
        skill.name,
        skill.description,
        skill.problems,
        health.failures,
        health.error,
        health.at,
        health.failing,
        skill.plugin,
    )
