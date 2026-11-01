"""The spending limits (limits.py) held to before every model call, from the token ledger (log.py), which TokenMeter's
check asks (meter.py). A call when a limit has been reached isn't made: it raises OverBudgetError, which ends the run
it's part of with what it says (which limit, what was spent, how to go on); a scheduled job's run is recorded as over
budget. After each call, a limit reached to WARN_SHARE is told once per limit and period (warned.py), to the chat
channels and the notifications feed (alerts.py).

Which limits a call counts against comes from its conversation: a job's run (`job:<name>:<time>`) against the job's
limit per run and per day, any other conversation against the limit per conversation, and every call, one outside a
conversation (titling, memory, Home) included, against the day's. A day is the user's (settings.timezone). Models with
no price count as nothing, as in the usage report."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.i18n import said
from assistant.core.usage import limits as spending_limits
from assistant.core.usage import warned
from assistant.core.usage.limits import Kind, SpendingLimits
from assistant.core.usage.log import UsageLog
from assistant.core.usage.tokens import job_of

# Reached to this share of a limit, it's told once.
WARN_SHARE = 0.8


@dataclass(frozen=True)
class Spending:
    """What a call counts against: a limit, what was spent towards it, and over what."""

    kind: Kind
    limit: float
    spent: float
    # The job, for its limits; "" otherwise.
    job: str = ""
    # The conversation or job run it's counted in; "" for the day overall.
    thread_id: str = ""
    # What it's counted over, for telling it once: the day for a daily limit, the run or conversation otherwise.
    period: str = ""

    @property
    def reached(self) -> bool:
        return self.spent >= self.limit

    @property
    def nearly(self) -> bool:
        return self.spent >= WARN_SHARE * self.limit


class OverBudgetError(Exception):
    """A model call not made: a spending limit was reached. Its message says which, for the user."""

    def __init__(self, spending: Spending) -> None:
        super().__init__(over_text(spending))
        self.spending = spending


class Budget:
    def __init__(self, ledger: UsageLog, store: BaseStore, warn: Callable[[Spending], Awaitable[None]]) -> None:
        """`warn` tells a limit nearly reached (alerts.py)."""
        self._ledger = ledger
        self._store = store
        self._warn = warn

    async def check(self, thread_id: str) -> None:
        """Before a model call in `thread_id` ("" outside a conversation). Raises OverBudgetError."""
        for spending in await self.spending(thread_id):
            if spending.reached:
                raise OverBudgetError(spending)

    async def after_call(self, thread_id: str) -> None:
        """After a model call in `thread_id` was recorded: tells each limit it nearly reached, once."""
        for spending in await self.spending(thread_id):
            if spending.nearly and await warned.first(self._store, _warned_key(spending)):
                await self._warn(spending)

    async def spent_today(self, now: datetime | None = None) -> float:
        """What every model call cost since the user's day started."""
        return await self._ledger.spent(since=_day(now or datetime.now(UTC))[1])

    async def spending(self, thread_id: str, now: datetime | None = None) -> list[Spending]:
        """The limits set that a call in `thread_id` counts against, the narrowest first, with what was spent."""
        limits = await spending_limits.load(self._store)
        if not limits.any:
            return []
        today, since = _day(now or datetime.now(UTC))
        job = job_of(thread_id) or ""
        found: list[Spending] = []
        if job:
            found += await self._measured(
                limits, Spending("job_run", 0, 0, job, thread_id, thread_id), thread_id=thread_id
            )
            found += await self._measured(limits, Spending("job_day", 0, 0, job, period=today), since=since, job=job)
        elif thread_id:
            conversation = Spending("conversation", 0, 0, thread_id=thread_id, period=thread_id)
            found += await self._measured(limits, conversation, thread_id=thread_id)
        found += await self._measured(limits, Spending("day", 0, 0, period=today), since=since)
        return found

    async def _measured(self, limits: SpendingLimits, spending: Spending, **counted: str) -> list[Spending]:
        """`spending` with its limit and what was spent towards it, counted in the ledger by `counted`; none when its
        limit is off."""
        limit = limits.of(spending.kind)
        if limit is None:
            return []
        return [replace(spending, limit=limit, spent=await self._ledger.spent(**counted))]


def over_text(spending: Spending) -> str:
    """What the run ends with when the limit is reached."""
    values = {"spent": dollars(spending.spent), "limit": dollars(spending.limit), "job": spending.job}
    if spending.kind == "job_run":
        return said("This run of the job {job} spent {spent}, its limit per run is {limit}: it stopped here.", **values)
    if spending.kind == "job_day":
        return said("The job {job} spent {spent} today, its daily limit is {limit}: this run stopped here.", **values)
    if spending.kind == "conversation":
        return said(
            "This conversation spent {spent}, its limit is {limit}, so the assistant stopped here. Raise or clear the "
            "limit in Settings → Model (/limits in the terminal app) to go on, or start a new conversation.",
            **values,
        )
    return said(
        "The assistant spent {spent} today, the daily limit is {limit}, so it stopped here. It goes on tomorrow, or "
        "once the limit is raised or cleared in Settings → Model (/limits in the terminal app).",
        **values,
    )


def dollars(amount: float) -> str:
    return f"US${amount:,.2f}"


def _warned_key(spending: Spending) -> str:
    """Once per limit and period; a limit changed meanwhile is told again."""
    return f"{spending.kind}:{spending.job}:{spending.period}:{spending.limit}"


def _day(now: datetime) -> tuple[str, str]:
    """The user's day `now` falls in, and when it started, in UTC as the ledger records calls."""
    local = now.astimezone(ZoneInfo(settings.timezone))
    start = datetime.combine(local.date(), time(), local.tzinfo)
    return local.date().isoformat(), start.astimezone(UTC).isoformat()
