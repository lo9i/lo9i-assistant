"""The clients connected to the daemon. A client counts as connected while it holds the /events
stream open, which every client does for its whole session."""

from datetime import UTC, datetime

from assistant.core.bus import EventBus
from assistant.protocol import ConnectedClient


class ClientRegistry:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._clients: dict[int, ConnectedClient] = {}
        self._next_key = 0

    def add(self, client_id: str, kind: str, transport: str) -> int:
        """Registers a connection and returns the key that removes it."""
        self._next_key += 1
        self._clients[self._next_key] = ConnectedClient(client_id, kind, transport, datetime.now(UTC).isoformat())
        self._bus.publish("clients")
        return self._next_key

    def remove(self, key: int) -> None:
        if self._clients.pop(key, None) is not None:
            self._bus.publish("clients")

    def list(self) -> list[ConnectedClient]:
        return sorted(self._clients.values(), key=lambda c: c.connected_at)
