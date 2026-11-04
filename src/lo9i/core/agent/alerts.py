"""Alerts for clients: MCP servers and skills that keep failing, and remote MCP servers whose sign-in
stopped working (core/health.py), listed until the user dismisses them or they work again. A server
that's turned off or removed, or a skill that was deleted, has none. And the latest health check's
(core/doctor/): causes that are new or growing, and a starting context too large, until dismissed. And the morning
briefing or a review that failed (core/proactive/failed.py), until dismissed or the next one works."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from lo9i.core.agent.base import ServiceBase
from lo9i.core.config import settings
from lo9i.core.doctor.model import DoctorAlert
from lo9i.core.health import Area, Health
from lo9i.core.mcp import servers
from lo9i.core.proactive import failed
from lo9i.core.proactive.failed import Failed
from lo9i.core.skills import store

__all__ = ["Alert", "AlertArea", "AlertsMixin"]

# doctor: the health check's (core/doctor/), named after the cause or the starting context. proactive: the briefing or
# a review that failed, named briefing, nightly or weekly.
AlertArea = Literal["mcp", "skill", "doctor", "proactive"]


@dataclass
class Alert:
    area: AlertArea
    name: str
    # Failures in a row, the last one and when (ISO 8601). A health check's: how often the cause happened.
    failures: int
    error: str
    at: str
    # failing (failures in a row), or signed_out (an MCP server waits for the user to sign in again). A health
    # check's: a new or growing cause, or the starting context too large.
    kind: Literal["failing", "signed_out", "new", "growing", "context"] = "failing"
    # What to show instead of the name, when it isn't one (a health check's cause).
    title: str = ""


class AlertsMixin(ServiceBase):
    async def alerts(self) -> list[Alert]:
        """The newest first."""
        enabled = {s.name for s in await servers.load_all(self._storage.store) if s.enabled}
        skills = {s.name for s in await asyncio.to_thread(store.saved_skills)}
        found = [
            *await self._alerts("mcp", enabled),
            *await self._alerts("skill", skills),
            *[_doctor_alert(a) for a in await self.doctor.alerts(settings.owner_id)],
            *[_proactive_alert(f) for f in await failed.failed(self._storage.store, settings.owner_id)],
        ]
        return sorted(found, key=lambda a: a.at, reverse=True)

    async def dismiss_alert(self, area: AlertArea, name: str) -> None:
        if area == "doctor":
            await self.doctor.dismiss(settings.owner_id, name)
        elif area == "proactive":
            await failed.dismiss(self._storage.store, settings.owner_id, name)
        else:
            await self._health.dismiss(area, name)

    async def _alerts(self, area: Area, names: set[str]) -> list[Alert]:
        health = await self._health.all(area)
        return [_alert(area, name, h) for name, h in health.items() if name in names and _shown(h)]


def _shown(health: Health) -> bool:
    return health.alerted and not health.dismissed


def _alert(area: Area, name: str, health: Health) -> Alert:
    kind = "signed_out" if health.signed_out else "failing"
    return Alert(area, name, health.failures, health.error, health.at, kind)


def _doctor_alert(alert: DoctorAlert) -> Alert:
    return Alert("doctor", alert.name, alert.count, alert.text, alert.at, alert.kind, alert.title)


def _proactive_alert(found: Failed) -> Alert:
    return Alert("proactive", found.work, 1, found.error, found.at)
