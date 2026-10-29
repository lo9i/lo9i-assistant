"""When to tell the user the allowance is running out: once when the premium requests' or chat's quota (whichever
has less left, unless both are unlimited) drops below LOW_PERCENT, and once more when it runs out, each at most
once per period, until the reset date changes. Running out tells it even when the low alert wasn't sent; the low
alert isn't sent after it. Short texts, as the user reads them on WhatsApp, in the language chosen
(core/language.py)."""

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from assistant.core.copilot_quota.quota import CopilotQuota, Quota
from assistant.core.i18n import Texts

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


def due(t: Texts, quota: CopilotQuota, sent: SentAlerts) -> Alert | None:
    """The alert to send now, if any."""
    lowest = quota.lowest()
    level = _level(lowest) if lowest else None
    if lowest is None or level is None:
        return None
    already = _this_period(quota, sent)
    if level in already or "out" in already:
        return None
    return Alert(level, _text(t, level, lowest, quota.reset_date))


def after(quota: CopilotQuota, sent: SentAlerts, alert: Alert) -> SentAlerts:
    """What's recorded once `alert` was sent."""
    return SentAlerts(period=quota.reset_date, levels=[*_this_period(quota, sent), alert.level])


def _this_period(quota: CopilotQuota, sent: SentAlerts) -> list[Level]:
    return sent.levels if sent.period == quota.reset_date else []


def _level(quota: Quota) -> Level | None:
    if quota.exhausted:
        return "out"
    return "low" if quota.percent_remaining < LOW_PERCENT else None


def _text(t: Texts, level: Level, quota: Quota, reset_date: str) -> str:
    renewal = t(" (renews on {day})", day=_short(t, reset_date)) if reset_date else ""
    if level == "out":
        return t("Copilot: this month's allowance is used up{renewal}.", renewal=renewal)
    return t(
        "Copilot: {percent}% of this month's allowance left{renewal}.", percent=quota.percent_left, renewal=renewal
    )


def _short(t: Texts, day: str) -> str:
    """11/1 for 2026-11-01; 1/11 in Spanish."""
    date = dt.date.fromisoformat(day)
    return t("{month}/{day}", month=date.month, day=date.day)
