"""Runs kept while an update installed (core/conversation/held.py), run once lo9i is back on it (daemon/held.py)."""

from collections.abc import AsyncIterator

from assistant.core.agent.handoffs import HandoffsMixin
from assistant.core.agent.session import Session
from assistant.core.agent.titles import TitlesMixin
from assistant.core.conversation import handoffs, held
from assistant.core.conversation.held import HeldRun
from assistant.core.events import Event


class HeldRunsMixin(HandoffsMixin, TitlesMixin):
    async def held_runs(self, user_id: str) -> list[HeldRun]:
        """The runs waiting, oldest first."""
        return await held.waiting(self._storage.store, user_id)

    async def drop_held_run(self, user_id: str, held_id: str) -> None:
        """One that won't run: what it was for is gone (a scheduled job deleted)."""
        await held.take(self._storage.store, user_id, held_id)

    async def run_held(self, session: Session, run: HeldRun) -> AsyncIterator[Event]:
        """Runs `run` as it would have run when it came; still kept, answered with Held, while runs are held again
        (an update going back at start), and nothing when it ran already."""
        async for event in self._run_with(session, lambda: self._held_events(session, run), run):
            yield event
        self._title_in_background(session)

    async def _held_events(self, session: Session, run: HeldRun) -> AsyncIterator[Event]:
        """A message for a handed-off agent goes to the agent the conversation is handed to now; to the assistant
        when it was taken back meanwhile."""
        turn = held.agent_turn(run.input)
        handoff = await handoffs.current(self._storage.store, session.user_id, session.thread_id)
        if turn is None:
            events = self._run_events(session, held.graph_input(run.input))
        elif handoff is not None:
            events = self._agent_turn(session, handoff, *turn)
        else:
            events = self._run_events(session, {"messages": [turn[0]]})
        async for event in events:
            yield event
