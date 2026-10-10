"""Sends the messages waiting in a conversation (core/conversation/queued.py) once its run ends: each as a
run of its own, announced like any other, so every app on the conversation shows it live. Ones left
waiting when the daemon stopped are sent when it starts."""

import asyncio

from assistant.core.agent import AssistantService, Session
from assistant.core.config import settings
from assistant.core.waiting import first
from assistant.daemon.runs import RunHub


class QueuedMessages:
    name = "queued messages"

    def __init__(self, service: AssistantService, hub: RunHub) -> None:
        self._service = service
        self._hub = hub

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

    async def _send_next(self, thread_id: str) -> None:
        waiting = await self._service.next_queued(settings.owner_id, thread_id)
        if waiting is None:
            return
        session = Session(settings.owner_id, waiting.channel, thread_id)
        self._hub.start(thread_id, self._service.send(session, waiting.text), waiting.channel, text=waiting.text)
