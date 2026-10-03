"""Alerts for clients: MCP servers and skills that keep failing (core/health.py), listed until the
user dismisses them or they work again. A server that's turned off or removed, or a skill that was
deleted, has none."""

import asyncio
from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.health import Area, Health
from assistant.core.mcp import servers
from assistant.core.skills import store

__all__ = ["Alert", "AlertsMixin"]


@dataclass
class Alert:
    area: Area
    name: str
    # Failures in a row, the last one and when (ISO 8601).
    failures: int
    error: str
    at: str


class AlertsMixin(ServiceBase):
    async def alerts(self) -> list[Alert]:
        """The newest first."""
        enabled = {s.name for s in await servers.load_all(self._storage.store) if s.enabled}
        skills = {s.name for s in await asyncio.to_thread(store.saved_skills)}
        found = [
            *await self._alerts("mcp", enabled),
            *await self._alerts("skill", skills),
        ]
        return sorted(found, key=lambda a: a.at, reverse=True)

    async def dismiss_alert(self, area: Area, name: str) -> None:
        await self._health.dismiss(area, name)

    async def _alerts(self, area: Area, names: set[str]) -> list[Alert]:
        health = await self._health.all(area)
        return [_alert(area, name, h) for name, h in health.items() if name in names and _shown(h)]


def _shown(health: Health) -> bool:
    return health.failing and not health.dismissed


def _alert(area: Area, name: str, health: Health) -> Alert:
    return Alert(area, name, health.failures, health.error, health.at)
