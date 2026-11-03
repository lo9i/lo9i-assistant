"""The assistant's own initiative for clients (core/proactive/): the briefing and reviews with their settings, the open
loops, and the kinds of suggestion the user muted. Every change is a Store write, which publishes `proactive`."""

from datetime import UTC, datetime

from assistant.core.agent.base import ServiceBase
from assistant.core.i18n import said
from assistant.core.proactive import loops, records
from assistant.core.proactive.model import (
    Briefing,
    LoopStatus,
    OpenLoop,
    ProactivePage,
    ProactiveSettings,
    Review,
    Suggestion,
)
from assistant.core.proactive.schedule import Work

__all__ = [
    "Briefing",
    "LoopNotFoundError",
    "LoopStatus",
    "OpenLoop",
    "ProactiveMixin",
    "ProactivePage",
    "ProactiveSettings",
    "Review",
    "Suggestion",
    "Work",
]


class LoopNotFoundError(LookupError):
    pass


class ProactiveMixin(ServiceBase):
    async def proactive_page(self, user_id: str) -> ProactivePage:
        store = self._storage.store
        return ProactivePage(
            settings=await records.load_settings(store, user_id),
            loops=await loops.all_loops(store, user_id),
            briefing=await records.latest_briefing(store, user_id),
            reviews=(await records.reviews(store, user_id))[:7],
            running=self.proactive_runs.running,
        )

    async def save_proactive_settings(self, user_id: str, wanted: ProactiveSettings) -> ProactivePage:
        await records.save_settings(self._storage.store, user_id, wanted)
        return await self.proactive_page(user_id)

    async def start_proactive(self, user_id: str, work: Work) -> ProactivePage:
        """Writes the briefing (and tells it) or a review now, in the background, unless it runs already. The
        briefing written now is the day's: the schedule doesn't send another that day."""
        self.proactive_runs.start(work, datetime.now(UTC))
        return await self.proactive_page(user_id)

    async def close_loop(
        self, user_id: str, loop_id: str, status: LoopStatus, stop_suggesting: bool = False
    ) -> ProactivePage:
        """Done, dismissed, or open again; with `stop_suggesting`, its kind is muted. Raises LoopNotFoundError."""
        closed = await loops.close(self._storage.store, user_id, loop_id, status)
        if closed is None:
            raise LoopNotFoundError(said("No open loop {loop_id}.", loop_id=loop_id))
        if stop_suggesting and closed.kind:
            await records.mute(self._storage.store, user_id, closed.kind)
        return await self.proactive_page(user_id)

    async def mute_kind(self, user_id: str, kind: str, muted: bool) -> ProactivePage:
        await records.mute(self._storage.store, user_id, kind, muted)
        return await self.proactive_page(user_id)
