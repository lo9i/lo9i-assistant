"""Skills from other coding agents for clients: list the ones on this computer and import the ones the user picks
(core/skills/imports/)."""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from assistant.core.agent.base import ServiceBase
from assistant.core.skills.imports import importing, listing, projects
from assistant.core.skills.imports.importing import ImportOutcome
from assistant.core.skills.imports.listing import Importable, Importables

__all__ = ["ImportOutcome", "Importable", "Importables", "SkillImportsMixin"]


class SkillImportsMixin(ServiceBase):
    async def importable_skills(self, user_id: str) -> Importables:
        """Claude Code's and Codex's skills here and in the projects the assistant knows."""
        known = await projects.known(self._storage.store, user_id)
        return await asyncio.to_thread(listing.listing, Path.home(), known)

    async def import_skills(self, user_id: str, ids: Sequence[str], replace: bool = False) -> list[ImportOutcome]:
        """Import the skills with these ids (Importable.id), updating those imported before. `replace`: a skill
        with the same name is replaced instead of the import getting another name."""
        known = await projects.known(self._storage.store, user_id)
        outcomes = await asyncio.to_thread(importing.import_skills, ids, replace, Path.home(), known)
        if any(o.action != importing.FAILED for o in outcomes):
            self.bus.publish("skills")
        return outcomes
