"""Spending limits on the token ledger: off until set, checked before every model call, a run over one ending with a
message that says which (a job's run recorded as over budget), and a limit nearly reached told once, in the
notifications feed and on the chat channels."""

from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata

from lo9i.core import notifications
from lo9i.core.config import settings
from lo9i.core.events import Error
from lo9i.core.jobs import store
from lo9i.core.usage.budget import OverBudgetError
from lo9i.core.usage.limits import SpendingLimits, SpendingLimitsError
from lo9i.core.usage.log import ModelCall
from lo9i.daemon.scheduler import Scheduler
from tests.conftest import collect
from tests.core.test_jobs import _job_due

# A dollar a thousand tokens, input or output, for the model the scripted replies come from.
_PRICES = {"unknown": {"input": 1000, "output": 1000}}


def _usage(input_tokens: int) -> UsageMetadata:
    return UsageMetadata(input_tokens=input_tokens, output_tokens=0, total_tokens=input_tokens)


def _costing(dollars: float, text: str = "ok", **fields) -> AIMessage:
    return AIMessage(text, usage_metadata=_usage(int(dollars * 1000)), **fields)


class _Chat:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> list[str]:
        self.sent.append(text)
        return ["1"]


@pytest.fixture(autouse=True)
def priced(monkeypatch):
    monkeypatch.setattr(settings, "model_prices", _PRICES)


async def test_limits_are_off_until_set_and_each_is_more_than_zero(service):
    status = await service.spending()
    assert status.limits == SpendingLimits() and not status.limits.any and status.spent_today == 0
    with pytest.raises(SpendingLimitsError):
        await service.set_spending_limits(SpendingLimits(day=0))
    changed = await service.set_spending_limits(SpendingLimits(conversation=2.5))
    assert changed.limits == SpendingLimits(conversation=2.5)


async def test_the_ledger_prices_what_was_spent_and_a_model_without_a_price_counts_as_nothing(service):
    ledger = service._storage.usage

    def call(model: str, thread_id: str, tokens: int) -> ModelCall:
        job = "news" if thread_id.startswith("job:news:") else None
        return ModelCall("reply", "", model, thread_id, "cli", job, None, tokens, 0, 0, 0, 0, False)

    await ledger.record_model_call(call("unknown", "owner:a", 1500), [])
    await ledger.record_model_call(call("local-model", "owner:a", 9000), [])
    await ledger.record_model_call(call("unknown", "job:news:2026-11-01T09:00:00", 500), [])
    assert await ledger.spent() == pytest.approx(2.0)
    assert await ledger.spent(thread_id="owner:a") == pytest.approx(1.5)
    assert await ledger.spent(job="news") == pytest.approx(0.5)
    assert await ledger.spent(since=(datetime.now(UTC) + timedelta(minutes=1)).isoformat()) == 0


async def test_a_conversation_over_its_limit_ends_its_run_before_the_model_is_called(service, script, caplog):
    await service.set_spending_limits(SpendingLimits(conversation=1.0))
    script._replies.append(_costing(1.0, "first"))
    session = await service.session("owner", "cli")
    await collect(service.send(session, "go"))
    events = await collect(service.send(session, "again"))
    error = events[-1]
    assert isinstance(error, Error) and error.over_budget
    assert error.message.startswith("This conversation spent US$1.00, its limit is US$1.00")
    assert (await service.token_report(7)).total.calls == 1
    # Not a fault: nothing for the health check to count.
    assert not [r for r in caplog.records if r.levelname == "WARNING" and "OverBudgetError" in r.getMessage()]


async def test_the_days_limit_nearly_reached_is_told_once_on_the_channels_and_in_the_feed(service, script):
    chat = _Chat()
    service.outbox.register("telegram", chat)
    await service.set_spending_limits(SpendingLimits(day=2.5))
    for _ in range(3):
        script._replies.append(_costing(1.0))
    session = await service.session("owner", "cli")
    for text in ("one", "two", "three"):
        await collect(service.send(session, text))
    assert chat.sent == [
        "The assistant has spent US$2.00 today of the US$2.50 daily limit. At the limit it stops; Settings → Model "
        "(/limits in the terminal app) changes it."
    ]
    [told] = [n for n in await notifications.recent(service.store, "owner") if n.kind == "spending"]
    assert (told.title, told.ok, told.text) == ("Spending limit", False, chat.sent[0])
    events = await collect(service.send(session, "four"))
    assert isinstance(events[-1], Error) and "the daily limit is US$2.50" in events[-1].message
    assert (await service.spending()).spent_today == pytest.approx(3.0)


async def test_a_limit_changed_is_told_again(service, script):
    await service.set_spending_limits(SpendingLimits(conversation=1.0))
    script._replies.append(_costing(0.9))
    session = await service.session("owner", "cli")
    await collect(service.send(session, "go"))
    await service.set_spending_limits(SpendingLimits(conversation=1.1))
    script._replies.append(_costing(0.01))
    await collect(service.send(session, "again"))
    told = [n for n in await notifications.recent(service.store, "owner") if n.kind == "spending"]
    assert len(told) == 2 and told[0].thread_id == session.thread_id


async def test_a_job_run_over_its_jobs_daily_limit_is_recorded_as_over_budget(service, script):
    now = await _job_due(service, script, minutes_ago=1)
    await service.set_spending_limits(SpendingLimits(job_day=0.5))
    call = {"name": "bash", "args": {"command": "echo hi"}, "id": "c1"}
    script._replies.append(_costing(1.0, "", tool_calls=[call]))
    scheduler = Scheduler(service)
    await scheduler.tick(now)
    for task in list(scheduler._running.values()):
        await task
    job = await store.load(service.store, "owner", "daily-news")
    assert job is not None and job.runs[-1].status == "over budget"
    assert job.runs[-1].summary.startswith("The job daily-news spent US$1.00 today, its daily limit is US$0.50")
    told = next(n for n in await notifications.recent(service.store, "owner") if n.kind == "job")
    assert told.text.startswith("Over budget: The job daily-news spent")


async def test_calls_outside_a_conversation_count_against_the_days_limit(service):
    await service.set_spending_limits(SpendingLimits(day=1.0, conversation=5.0))
    ledger = service._storage.usage
    await ledger.record_model_call(ModelCall("title", "", "unknown", "", "", None, None, 1000, 0, 0, 0, 0, False), [])
    with pytest.raises(OverBudgetError) as raised:
        await service._budget.check("")
    assert raised.value.spending.kind == "day"
    with pytest.raises(OverBudgetError):
        await service._budget.check("owner:abc")
