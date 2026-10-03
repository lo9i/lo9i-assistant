"""The clients connected to the daemon, and the conversation each one is on. A client counts as
connected while it holds the /events stream open, which every client does for its whole session.

A conversation no client is on any more is left, which archives it: right away when its client
moves to another conversation, and after a grace period when its client disconnects, since a
reloaded page or a client reconnecting after a restart comes back to it. A client can hold more
conversations under ids made from its own (CLIENT_ID_PART); they're left with it."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from assistant.core.bus import EventBus
from assistant.protocol import CLIENT_ID_PART, ConnectedClient

_LEAVE_GRACE_SECONDS = 30


class ClientRegistry:
    def __init__(
        self, bus: EventBus, leave: Callable[[str], None], grace_seconds: float = _LEAVE_GRACE_SECONDS
    ) -> None:
        self._bus = bus
        self._leave = leave
        self._grace_seconds = grace_seconds
        self._clients: dict[int, ConnectedClient] = {}
        self._next_key = 0
        # Client id -> the conversation it's on.
        self._threads: dict[str, str] = {}

    def add(self, client_id: str, kind: str, transport: str, device_id: str = "") -> int:
        """Registers a connection and returns the key that removes it."""
        self._next_key += 1
        now = datetime.now(UTC).isoformat()
        self._clients[self._next_key] = ConnectedClient(client_id, kind, transport, now, device_id)
        self._bus.publish("clients")
        return self._next_key

    def remove(self, key: int) -> None:
        client = self._clients.pop(key, None)
        if client is None:
            return
        self._bus.publish("clients")
        if client.id and not self._connected(client.id):
            for held in self._held_by(client.id):
                self._left_later(self._threads.pop(held))

    def on(self, thread_id: str) -> list[str]:
        """The ids of the clients on this conversation."""
        return [client_id for client_id, on in self._threads.items() if on == thread_id]

    def list(self) -> list[ConnectedClient]:
        clients = [replace(c, thread_id=self._threads.get(c.id, "")) for c in self._clients.values()]
        return sorted(clients, key=lambda c: c.connected_at)

    def on_thread(self, client_id: str, thread_id: str) -> None:
        """The client is now on this conversation: it started, resumed or wrote to it."""
        if not client_id:
            return
        previous = self._threads.get(client_id)
        if previous == thread_id:
            return
        self._threads[client_id] = thread_id
        # Session lists show which conversation each client is on.
        self._bus.publish("clients")
        if previous is not None:
            self._leave_if_unused(previous)

    def _left_later(self, thread_id: str | None) -> None:
        if thread_id is not None:
            asyncio.get_running_loop().call_later(self._grace_seconds, self._leave_if_unused, thread_id)

    def _leave_if_unused(self, thread_id: str) -> None:
        if thread_id not in self._threads.values():
            self._leave(thread_id)

    def _held_by(self, client_id: str) -> tuple[str, ...]:
        """The ids this client holds conversations under: its own, and those made from it."""
        return tuple(held for held in self._threads if _owner(held) == client_id)

    def _connected(self, client_id: str) -> bool:
        return any(c.id == client_id for c in self._clients.values())


def _owner(client_id: str) -> str:
    return client_id.split(CLIENT_ID_PART, 1)[0]
