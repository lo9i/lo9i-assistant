"""A channel chat's runs (core/channels/chat/conversations.py) as daemon runs, so every client sees
them live as it would a run the apps started; and the other way, a run the daemon starts on its own in a
channel's conversation shown in that channel's chat (`ChannelMirrors`)."""

from collections.abc import AsyncIterator

from assistant.core.channels.chat.conversations import ChannelChats
from assistant.core.events import Event
from assistant.core.outbox import Outbox
from assistant.daemon.runs import Run, RunHub
from assistant.protocol import event_from_dict


class ChannelRuns:
    def __init__(self, hub: RunHub) -> None:
        self._hub = hub

    async def follow(
        self,
        channel: str,
        thread_id: str,
        events: AsyncIterator[Event],
        text: str,
        brief: str = "",
        held: str = "",
        carried: str = "",
    ) -> AsyncIterator[Event]:
        run = self._hub.start(thread_id, events, channel, text=text, brief=brief, held=held, carried=carried)
        async for event in followed(self._hub, run):
            yield event


class ChannelMirrors:
    """Shows a run the daemon started on its own (daemon/queued.py) in the chat of the channel its conversation was
    on, while that channel is connected; on any other channel (an app's), the apps show it already."""

    def __init__(self, hub: RunHub, chats: ChannelChats, outbox: Outbox) -> None:
        self._hub = hub
        self._chats = chats
        self._outbox = outbox

    def mirror(self, run: Run) -> None:
        if run.channel in self._outbox.channels:
            self._chats.spawn(self._chats.mirror(run.channel, run.thread_id, followed(self._hub, run), run.text))


async def followed(hub: RunHub, run: Run) -> AsyncIterator[Event]:
    """The run's events from its start, until it ends."""
    async for _, event in hub.follow(run, 0):
        if event is None:
            return
        yield event_from_dict(event)
