"""Whether MCP servers and skills keep failing: per server and per skill, the failures in a row and
the last one, in the Store. A success clears the count and keeps the last failure for reference.
Reaching FAILING_AFTER in a row publishes a `failing` event, which clients show as an alert, and
makes it an alert the web app keeps listing until the user dismisses it or it works again."""

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus

# Failures in a row before the user is told: fewer would alert on a model's typo or a blip.
FAILING_AFTER = 3
_ERROR_CHARS = 500

Area = Literal["mcp", "skill"]
_NAMESPACES: dict[Area, tuple[str, ...]] = {"mcp": ("mcp_health",), "skill": ("skill_health",)}


@dataclass
class Health:
    # Failures in a row; 0 once it works again.
    failures: int = 0
    # The last failure and when it happened (ISO 8601), "" if it never failed.
    error: str = ""
    at: str = ""
    # The user dismissed the alert; cleared when it works again, so a later run of failures alerts anew.
    dismissed: bool = False

    @property
    def failing(self) -> bool:
        """Failing enough that the user was alerted."""
        return self.failures >= FAILING_AFTER


class HealthLog:
    """One per service: its lock keeps writes from MCP calls, skill scripts and dismissals apart."""

    def __init__(self, store: BaseStore, bus: EventBus) -> None:
        self._store = store
        self._bus = bus
        # Parallel tool calls update the same record; each read and write holds this, so none is lost.
        self._lock = asyncio.Lock()

    async def failed(self, area: Area, name: str, error: str) -> None:
        async with self._lock:
            previous = await self.get(area, name)
            error = error.strip()[-_ERROR_CHARS:]
            health = Health(previous.failures + 1, error, datetime.now(UTC).isoformat(), previous.dismissed)
            await self._store.aput(_NAMESPACES[area], name, asdict(health))
        if health.failures == FAILING_AFTER:
            self._bus.publish("failing", area=area, name=name, error=health.error)

    async def succeeded(self, area: Area, name: str) -> None:
        """Clears the count. Writes only when it was failing, so a working call costs one read."""
        async with self._lock:
            previous = await self.get(area, name)
            if previous.failures:
                await self._store.aput(_NAMESPACES[area], name, asdict(Health(0, previous.error, previous.at)))

    async def dismiss(self, area: Area, name: str) -> None:
        """Stop listing its alert until it works and then keeps failing again."""
        async with self._lock:
            previous = await self.get(area, name)
            if previous.failing and not previous.dismissed:
                previous.dismissed = True
                await self._store.aput(_NAMESPACES[area], name, asdict(previous))

    async def get(self, area: Area, name: str) -> Health:
        item = await self._store.aget(_NAMESPACES[area], name)
        return Health(**item.value) if item else Health()

    async def all(self, area: Area) -> dict[str, Health]:
        items = await self._store.asearch(_NAMESPACES[area], limit=10_000)
        return {item.key: Health(**item.value) for item in items}

    async def forget(self, area: Area, name: str) -> None:
        """For a server or skill that was removed."""
        await self._store.adelete(_NAMESPACES[area], name)
