"""Home for clients (core/home/): the sections with their last results, a refresh in the background, the clients
showing it, the sections the user edits, and the conversations pinned to it."""

from collections.abc import Collection

from assistant.core import conversations, inbox
from assistant.core.agent.base import ServiceBase
from assistant.core.agent.threads import ConversationError
from assistant.core.home import pins, results, sections
from assistant.core.home.model import HomeCard, HomeItem, HomePage, HomeSection, SectionResult
from assistant.core.home.sections import HomeSectionsError

__all__ = [
    "HomeCard",
    "HomeItem",
    "HomeMixin",
    "HomePage",
    "HomePinError",
    "HomeSection",
    "HomeSectionsError",
    "SectionResult",
]


class HomePinError(ValueError):
    """A conversation that can't be pinned to Home. The text says why."""


class HomeMixin(ServiceBase):
    async def home(self, user_id: str) -> HomePage:
        return await self.home_refresh.page(user_id)

    async def refresh_home(self, user_id: str, force: bool = False) -> HomePage:
        """Starts a refresh in the background unless one runs or, unforced, the last one is fresh."""
        await self.home_refresh.refresh(user_id, force)
        return await self.home_refresh.page(user_id)

    def watch_home(self, client_id: str) -> None:
        """The client shows Home now: it's kept current while it does (core/home/schedule.py)."""
        self.home_schedule.watch(client_id)

    def unwatch_home(self, client_id: str) -> None:
        """The client stopped showing Home, or disconnected."""
        self.home_schedule.unwatch(client_id)

    async def save_home_sections(self, user_id: str, wanted: list[HomeSection]) -> HomePage:
        """Saves them and builds the ones that are new or changed; a removed section's result goes. Raises
        HomeSectionsError."""
        before = {s.id: s for s in await sections.load(self._storage.store, user_id)}
        saved = await sections.save(self._storage.store, user_id, wanted)
        await self._sections_changed(user_id, before, saved)
        return await self.home_refresh.page(user_id)

    async def reset_home_sections(self, user_id: str) -> HomePage:
        """Back to the built-in sections."""
        before = {s.id: s for s in await sections.load(self._storage.store, user_id)}
        await self._sections_changed(user_id, before, await sections.reset(self._storage.store, user_id))
        return await self.home_refresh.page(user_id)

    async def home_pins(self, user_id: str) -> list[str]:
        """The conversations pinned to Home, the first pinned first."""
        return await pins.load(self._storage.store, user_id)

    async def pin_to_home(self, user_id: str, thread_id: str) -> list[str]:
        """Pins it after the others. Raises ConversationError for an unknown one, HomePinError for the inbox,
        which isn't a conversation to read."""
        if await conversations.load(self._storage.store, user_id, thread_id) is None:
            raise ConversationError(f"No conversation {thread_id}.")
        if thread_id == await inbox.current(self._storage.store, user_id):
            raise HomePinError("The inbox can't be pinned to Home.")
        return await self._pins_changed(user_id, await pins.pin(self._storage.store, user_id, thread_id))

    async def unpin_from_home(self, user_id: str, thread_id: str) -> list[str]:
        return await self._pins_changed(user_id, await pins.unpin(self._storage.store, user_id, thread_id))

    async def _pins_changed(self, user_id: str, pinned: list[str]) -> list[str]:
        """The Conversations card is built again for the apps that show its result."""
        await self.home_refresh.refresh(user_id, only=[sections.CONVERSATIONS])
        return pinned

    async def _sections_changed(self, user_id: str, before: dict[str, HomeSection], now: list[HomeSection]) -> None:
        for removed in before.keys() - {s.id for s in now}:
            await results.forget(self._storage.store, user_id, removed)
        changed = _changed(before, now)
        if changed:
            await self.home_refresh.refresh(user_id, only=changed)


def _changed(before: dict[str, HomeSection], now: list[HomeSection]) -> Collection[str]:
    """New sections, and those whose instructions or plugins changed: a new title alone needs no new result."""
    return [s.id for s in now if (b := before.get(s.id)) is None or (b.prompt, b.plugins) != (s.prompt, s.plugins)]
