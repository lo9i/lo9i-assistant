"""When to tell the user the allowance is running out: once when the premium requests' or chat's quota (whichever
has less left, unless both are unlimited) drops below LOW_PERCENT, and once more when it runs out, each at most
once per period, until the reset date changes. Running out tells it even when the low alert wasn't sent; the low
alert isn't sent after it. Short Spanish texts, as the user reads them on WhatsApp."""

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from assistant.core.copilot_quota.quota import CopilotQuota, Quota

LOW_PERCENT = 20

Level = Literal["low", "out"]


@dataclass(frozen=True)
class Alert:
    level: Level
    text: str


class SentAlerts(BaseModel):
    """The alerts sent in a period."""

    # The reset date the period ends on.
    period: str = ""
    levels: list[Level] = []


def due(quota: CopilotQuota, sent: SentAlerts) -> Alert | None:
    """The alert to send now, if any."""
    lowest = quota.lowest()
    level = _level(lowest) if lowest else None
    if lowest is None or level is None:
        return None
    already = _this_period(quota, sent)
    if level in already or "out" in already:
        return None
    return Alert(level, _text(level, lowest, quota.reset_date))


def after(quota: CopilotQuota, sent: SentAlerts, alert: Alert) -> SentAlerts:
    """What's recorded once `alert` was sent."""
    return SentAlerts(period=quota.reset_date, levels=[*_this_period(quota, sent), alert.level])


def _this_period(quota: CopilotQuota, sent: SentAlerts) -> list[Level]:
    return sent.levels if sent.period == quota.reset_date else []


def _level(quota: Quota) -> Level | None:
    if quota.exhausted:
        return "out"
    return "low" if quota.percent_remaining < LOW_PERCENT else None


def _text(level: Level, quota: Quota, reset_date: str) -> str:
    renewal = f" (se renueva el {_short(reset_date)})" if reset_date else ""
    if level == "out":
        return f"Copilot: se agotó el cupo mensual{renewal}."
    return f"Copilot: queda {quota.percent_left}% del cupo mensual{renewal}."


def _short(day: str) -> str:
    """1/11 for 2026-11-01."""
    date = dt.date.fromisoformat(day)
    return f"{date.day}/{date.month}"
