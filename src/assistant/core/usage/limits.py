"""How much the model calls may spend, in US dollars as the usage report prices them (prices.py): per run of a scheduled
job, per job a day, per conversation and overall a day, the day being the user's (settings.timezone). Each is off
(None) until the user sets it in Settings → Model (/limits in the terminal app). One Store record. budget.py checks
them before every model call."""

from dataclasses import asdict, dataclass, fields
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core.i18n import said

_NAMESPACE = ("settings",)
_KEY = "spending_limits"

# Which limit: a job's run, a job's day, a conversation, or the day overall.
Kind = Literal["job_run", "job_day", "conversation", "day"]


@dataclass(frozen=True)
class SpendingLimits:
    """US dollars; None is no limit."""

    job_run: float | None = None
    job_day: float | None = None
    conversation: float | None = None
    day: float | None = None

    @property
    def any(self) -> bool:
        return any(getattr(self, f.name) is not None for f in fields(self))

    def of(self, kind: Kind) -> float | None:
        return getattr(self, kind)


class SpendingLimitsError(ValueError):
    """A limit that isn't more than 0."""


async def load(store: BaseStore) -> SpendingLimits:
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return SpendingLimits()
    known = {f.name for f in fields(SpendingLimits)}
    return SpendingLimits(**{k: None if v is None else float(v) for k, v in item.value.items() if k in known})


async def save(store: BaseStore, limits: SpendingLimits) -> SpendingLimits:
    """Raises SpendingLimitsError."""
    if any(value is not None and value <= 0 for value in asdict(limits).values()):
        raise SpendingLimitsError(said("A limit is an amount more than 0; leave it empty for no limit."))
    await store.aput(_NAMESPACE, _KEY, asdict(limits))
    return limits
