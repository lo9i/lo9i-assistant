import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from assistant.client.daemon_client.chat import ChatBase
from assistant.client.daemon_client.reconnect import ReconnectPolicy, resumable_events

# Clients keep this stream for their whole session, so they wait out a daemon restart.
_RECONNECT = ReconnectPolicy(delay_seconds=2)


class EventsMixin(ChatBase):
    async def events(
        self, on_open: Callable[[], None] = lambda: None, on_lost: Callable[[], None] = lambda: None
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """(kind, data) for daemon events from now on, for as long as the caller keeps reading.
        Reconnects, resuming after the last event, if the daemon restarts. `on_open` and `on_lost` say when
        the stream opens and when it drops, so the app can say the daemon is away."""
        events = resumable_events(self._transport, "/events", _RECONNECT, after="", on_open=on_open, on_lost=on_lost)
        async for kind, data in events:
            yield kind, json.loads(data)
