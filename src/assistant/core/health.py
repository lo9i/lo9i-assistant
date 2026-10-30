"""Whether MCP servers and skills keep failing: per server and per skill, the failures in a row and
the last one, in the Store. A success clears the count and keeps the last failure for reference.
Reaching FAILING_AFTER in a row publishes a `failing` event, which clients show as an alert, and
makes it an alert the web app keeps listing until the user dismisses it or it works again.

A remote MCP server whose sign-in stopped working (its refresh was refused, or it was revoked) is an
alert too, at once: it publishes a `signed_out` event and stays until the user signs in again or
dismisses it. A server that was never signed in isn't one: the user is adding it and sees it asks."""

import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core import i18n
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
    # An MCP server's sign-in stopped working: it waits for the user to sign in again.
    signed_out: bool = False

    @property
    def failing(self) -> bool:
        """Failing enough that the user was alerted."""
        return self.failures >= FAILING_AFTER

    @property
    def alerted(self) -> bool:
        """The user was alerted, by failures in a row or a lost sign-in."""
        return self.failing or self.signed_out


class HealthLog:
    """One per service: its lock keeps writes from MCP calls, skill scripts and dismissals apart."""

    def __init__(self, store: BaseStore, bus: EventBus) -> None:
        self._store = store
        self._bus = bus
        # Parallel tool calls update the same record; each read and write holds this, so none is lost.
        self._lock = asyncio.Lock()

    async def failed(self, area: Area, name: str, error: str) -> None:
        """`error` written with `said` is kept in the language chosen (core/i18n)."""
        error = await self._kept(error)
        async with self._lock:
            previous = await self.get(area, name)
            health = replace(previous, failures=previous.failures + 1, error=error, at=datetime.now(UTC).isoformat())
            await self._store.aput(_NAMESPACES[area], name, asdict(health))
        if health.failures == FAILING_AFTER:
            self._bus.publish("failing", area=area, name=name, error=health.error)

    async def succeeded(self, area: Area, name: str) -> None:
        """Clears the count. Writes only when it was failing, so a working call costs one read."""
        async with self._lock:
            previous = await self.get(area, name)
            if previous.failures:
                cleared = replace(previous, failures=0, dismissed=previous.dismissed and previous.signed_out)
                await self._store.aput(_NAMESPACES[area], name, asdict(cleared))

    async def signed_out(self, name: str, error: str) -> None:
        """An MCP server's sign-in stopped working. Alerts once, until it's signed in again."""
        error = await self._kept(error)
        async with self._lock:
            previous = await self.get("mcp", name)
            if previous.signed_out:
                return
            now = datetime.now(UTC).isoformat()
            health = replace(previous, error=error, at=now, dismissed=False, signed_out=True)
            await self._store.aput(_NAMESPACES["mcp"], name, asdict(health))
        self._bus.publish("signed_out", name=name, error=health.error)

    async def _kept(self, error: str) -> str:
        return (await i18n.chosen(self._store)).shown(error).strip()[-_ERROR_CHARS:]

    async def signed_in(self, name: str) -> None:
        """An MCP server connected: a lost sign-in is back. Writes only when it was lost."""
        async with self._lock:
            previous = await self.get("mcp", name)
            if previous.signed_out:
                back = replace(previous, signed_out=False, dismissed=previous.dismissed and previous.failing)
                await self._store.aput(_NAMESPACES["mcp"], name, asdict(back))

    async def dismiss(self, area: Area, name: str) -> None:
        """Stop listing its alert until it works and then keeps failing again, or signs in and loses it again."""
        async with self._lock:
            previous = await self.get(area, name)
            if previous.alerted and not previous.dismissed:
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
