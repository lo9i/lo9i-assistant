"""Home for clients (core/home/): the sections with their last results, a refresh in the background, the clients
showing it, and the sections the user edits."""

from collections.abc import Collection

from assistant.core.agent.base import ServiceBase
from assistant.core.home import results, sections
from assistant.core.home.model import HomeCard, HomeItem, HomePage, HomeSection, SectionResult
from assistant.core.home.sections import HomeSectionsError

__all__ = [
    "HomeCard",
    "HomeItem",
    "HomeMixin",
    "HomePage",
    "HomeSection",
    "HomeSectionsError",
    "SectionResult",
]


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

    async def _sections_changed(self, user_id: str, before: dict[str, HomeSection], now: list[HomeSection]) -> None:
        for removed in before.keys() - {s.id for s in now}:
            await results.forget(self._storage.store, user_id, removed)
        changed = _changed(before, now)
        if changed:
            await self.home_refresh.refresh(user_id, only=changed)


def _changed(before: dict[str, HomeSection], now: list[HomeSection]) -> Collection[str]:
    """New sections, and those whose instructions or plugins changed: a new title alone needs no new result."""
    return [s.id for s in now if (b := before.get(s.id)) is None or (b.prompt, b.plugins) != (s.prompt, s.plugins)]
