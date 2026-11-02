"""The apps' About you step (core/memory/about_you.py): shown at first run until the profile has a name, and
from Settings later. Its answers go to the profile at once, and the extras' plugins for what the user wants
help with come back to offer."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.memory import MemoryEditError
from assistant.core.i18n import said
from assistant.core.memory import about_you, facts, profile
from assistant.core.memory.about_you import AboutYou
from assistant.core.repositories.suggested import Suggested, suggested

__all__ = ["AboutYou", "AboutYouMixin", "AboutYouStatus", "Suggested"]


@dataclass(frozen=True)
class AboutYouStatus:
    answers: AboutYou
    # No name in the profile yet: the apps show the step on their own.
    needed: bool


class AboutYouMixin(ServiceBase):
    async def about_you(self, user_id: str) -> AboutYouStatus:
        answers = about_you.read(await profile.load(self._storage.store, user_id))
        return AboutYouStatus(answers, needed=not answers.name)

    async def save_about_you(self, user_id: str, answers: AboutYou) -> list[Suggested]:
        """Raises MemoryEditError without a name. Like the assistant's own changes, the answers reach the
        system prompt from the next epoch; an item they push out of a full section is kept as a fact."""
        if not answers.name.strip():
            raise MemoryEditError(said("Write your name."))
        store = self._storage.store
        updated, overflow = about_you.written(await profile.load(store, user_id), answers)
        await profile.save(store, user_id, updated)
        for text in overflow:
            await facts.add(store, user_id, text)
        return await suggested(store, answers.help_with)
