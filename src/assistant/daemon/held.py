"""Runs the runs kept while an update installed (core/conversation/held.py), in the order they came, each to its end
before the next: when the daemon starts, back on the update, and when an update failed and let runs through again
(a `runs_released` event). Each shows where it came from (`Origin`): a channel's chat runs it again there
(`ChannelChats.replay`), a scheduled job's run is the scheduler's, which records it on its job (`Scheduler.replay`),
and any other runs as a run announced to every app, which show it as one started elsewhere. A message the inbox
sends on then is sent on from here, as the app that sent it would have, and that app's client is told where it went
(a `sent_on` event), so it goes there as it does after sending one on itself."""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol

from assistant.core.agent import AssistantService, Session
from assistant.core.config import settings
from assistant.core.conversation import held
from assistant.core.conversation.held import HeldRun
from assistant.core.events import Dispatched
from assistant.core.waiting import first
from assistant.daemon.runs import Run, RunHub
from assistant.protocol import event_from_dict, event_to_dict

logger = logging.getLogger(__name__)


class Replayer(Protocol):
    async def replay(self, run: HeldRun) -> None:
        """Runs `run` and shows it where it came from; returns once it ended."""
        ...


class HeldRuns:
    name = "held runs"

    def __init__(self, service: AssistantService, hub: RunHub, replayers: Mapping[str, Replayer]) -> None:
        """`replayers`: who runs each kind of origin again besides the apps (held.CHAT, held.JOB)."""
        self._service = service
        self._replayers = {held.APPS: _AppRuns(service, hub), **replayers}

    async def run(self, stop: asyncio.Event) -> None:
        # Taken before replaying, so a release meanwhile is heard.
        after = self._service.bus.last_id
        await first(stop.wait(), self._replay_and_follow(after))

    async def _replay_and_follow(self, after: int) -> None:
        await self._replay()
        async for event in self._service.bus.subscribe(after):
            if event.kind == "runs_released":
                await self._replay()

    async def _replay(self) -> None:
        """Stops while runs are held again (an unfinished update going back at start, which restarts after)."""
        for run in await self._service.held_runs(settings.owner_id):
            if self._service.runs_held():
                return
            replayer = self._replayers.get(run.origin.kind, self._replayers[held.APPS])
            try:
                await replayer.replay(run)
            except Exception:
                logger.exception("A run kept while an update installed failed in %s", run.thread_id)


class _AppRuns:
    """A run announced to every app, as any run started elsewhere: the app that sent it shows it too."""

    def __init__(self, service: AssistantService, hub: RunHub) -> None:
        self._service = service
        self._hub = hub

    async def replay(self, run: HeldRun) -> None:
        session = Session(settings.owner_id, run.channel, run.thread_id, run.origin)
        shown = {"text": run.text, "notice": run.notice, "brief": run.brief, "resent": run.resent, "held": run.id}
        started = self._hub.start(run.thread_id, self._service.run_held(session, run), run.channel, **shown)
        if dispatched := await self._until_finished(started):
            await self._send_on(run, dispatched)

    async def _send_on(self, run: HeldRun, dispatched: Dispatched) -> None:
        """To the conversation the inbox sent the message to, or a new one, as the client that wrote it: announced
        with its id, and that client told where it went."""
        thread_id = dispatched.thread_id or await self._service.new_thread(settings.owner_id)
        client_id = held.client_of(run.origin)
        session = Session(settings.owner_id, run.channel, thread_id, run.origin)
        events = self._service.send_dispatched(session, dispatched.id)
        sent = self._hub.start(thread_id, events, run.channel, client_id, dispatched.text, brief=dispatched.brief)
        if client_id:
            self._tell(client_id, run, sent, replace(dispatched, thread_id=thread_id))
        await self._until_finished(sent)

    def _tell(self, client_id: str, run: HeldRun, sent: Run, dispatched: Dispatched) -> None:
        """While it's still on the conversation it wrote in (`from_thread_id`), the client goes where the message
        went and shows `run_id` there, as after a Dispatched of its own run."""
        where = {"client_id": client_id, "from_thread_id": run.thread_id, "run_id": sent.id, "channel": run.channel}
        self._service.bus.publish("sent_on", **where, dispatched=event_to_dict(dispatched))

    async def _until_finished(self, run: Run) -> Dispatched | None:
        """Where the inbox sent the run's message on, if it did."""
        dispatched = None
        async for _, event in self._hub.follow(run, 0):
            if event is not None and isinstance(shown := event_from_dict(event), Dispatched):
                dispatched = shown
        return dispatched
