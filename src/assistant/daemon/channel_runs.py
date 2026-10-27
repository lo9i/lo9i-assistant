"""A channel chat's runs (core/channels/chat/conversations.py) as daemon runs, so every client sees
them live as it would a run the apps started."""

from collections.abc import AsyncIterator

from assistant.core.events import Event
from assistant.daemon.runs import RunHub
from assistant.protocol import event_from_dict


class ChannelRuns:
    def __init__(self, hub: RunHub) -> None:
        self._hub = hub

    async def follow(
        self, channel: str, thread_id: str, events: AsyncIterator[Event], text: str, brief: str = ""
    ) -> AsyncIterator[Event]:
        run = self._hub.start(thread_id, events, channel, text=text, brief=brief)
        async for _, event in self._hub.follow(run, 0):
            if event is None:
                return
            yield event_from_dict(event)
