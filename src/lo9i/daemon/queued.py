"""Sends the messages waiting in a conversation (core/conversation/queued.py) once nothing runs there: when
one is queued, or when its run ends, each as a run of its own, announced like any other, so every app on the
conversation shows it live. A follow-up on background work runs with no message from the user
(core/agent/follow_ups.py). Ones left waiting when the daemon stopped are sent when it starts.

While a restart or stop is asked for (daemon/shutdown.py) they wait: a run started then would be one more it waits
for, and they're kept in the Store, so they go once the daemon is back, or at once when it's taken back. Those of a
conversation whose messages go first (core/ending.py: a coding task the user chose to send now) go all the same, and
the restart waits for them, until the conversation has none left once its run ended.

A run sent from a chat channel (the conversation was on Telegram when its task or follow-up was queued) shows in
that channel's chat too, as the apps show it (daemon/channel_runs.py)."""

import asyncio
from typing import Protocol

from lo9i.core.agent import AssistantService, Session
from lo9i.core.config import settings
from lo9i.core.waiting import first
from lo9i.daemon.runs import Run, RunHub


class Ending(Protocol):
    """The daemon's restart or stop (daemon/shutdown.py::Shutdown)."""

    def asked(self) -> bool: ...


class Mirrors(Protocol):
    """Shows a run in the chat of its channel, when that's a chat channel (daemon/channel_runs.py::ChannelMirrors)."""

    def mirror(self, run: Run) -> None: ...


class QueuedMessages:
    name = "queued messages"

    def __init__(self, service: AssistantService, hub: RunHub, ending: Ending, mirrors: Mirrors) -> None:
        self._service = service
        self._hub = hub
        self._ending = ending
        self._mirrors = mirrors

    async def run(self, stop: asyncio.Event) -> None:
        # Taken before sending, so a run that ends meanwhile is heard.
        after = self._service.bus.last_id
        for thread_id in await self._service.queued_threads(settings.owner_id):
            await self._send_next(thread_id)
        await first(stop.wait(), self._follow(after))

    async def _follow(self, after: int) -> None:
        async for event in self._service.bus.subscribe(after):
            if event.kind == "run_finished":
                await self._send_next(str(event.data["thread_id"]))
            elif event.kind == "queued_messages" or (event.kind == "ending" and event.data.get("taken_back")):
                await self._send_where_idle()

    async def _send_where_idle(self) -> None:
        """A message was queued: one in a conversation with a run in progress waits for its end."""
        running = {run.thread_id for run in self._hub.running()}
        for thread_id in await self._service.queued_threads(settings.owner_id):
            if thread_id not in running:
                await self._send_next(thread_id)

    async def _send_next(self, thread_id: str) -> None:
        first = self._service.ending
        if self._ending.asked() and not first.goes_first(thread_id):
            return
        waiting = await self._service.next_queued(settings.owner_id, thread_id)
        if waiting is None:
            first.sent(thread_id)
            return
        session = Session(settings.owner_id, waiting.channel, thread_id)
        if waiting.follow_up:
            # The message isn't the user's: the apps show its notice from the conversation, not as theirs.
            follow_up = self._service.follow_up(session, waiting.text)
            self._mirrors.mirror(self._hub.start(thread_id, follow_up, waiting.channel, notice=waiting.text))
            return
        # A coding task is the assistant's: the apps show it as one, not as the user's message; messages sent again
        # show as those, not as new ones.
        shown = {"brief": waiting.brief, "resent": waiting.resent}
        sent = self._service.send(session, waiting.text, saved=waiting.files, **shown)
        self._mirrors.mirror(self._hub.start(thread_id, sent, waiting.channel, text=waiting.text, **shown))
