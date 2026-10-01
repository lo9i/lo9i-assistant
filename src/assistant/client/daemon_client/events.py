import json
from collections.abc import AsyncIterator
from typing import Any

from assistant.client.daemon_client.chat import ChatBase
from assistant.client.daemon_client.reconnect import ReconnectPolicy, resumable_events

# Clients keep this stream for their whole session, so they wait out a daemon restart.
_RECONNECT = ReconnectPolicy(delay_seconds=2)


class EventsMixin(ChatBase):
    async def events(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """(kind, data) for daemon events from now on, for as long as the caller keeps reading.
        Reconnects, resuming after the last event, if the daemon restarts."""
        async for kind, data in resumable_events(self._transport, "/events", _RECONNECT, after=""):
            yield kind, json.loads(data)
