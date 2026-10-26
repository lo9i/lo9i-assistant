"""The doctor: a day's log records grouped by cause, runs that failed and tool calls left without results in the
conversations' checkpoints, the context a new conversation starts with, what changed since the day before, the
alerts and notification it gives, known noise left out, and the daemon checking each day once it ended."""

import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import StateSnapshot

from assistant.core import conversations, notifications
from assistant.core.config import settings
from assistant.core.conversation.turn_header import header_block
from assistant.core.conversations import Conversation
from assistant.core.doctor import conversation_causes, records
from assistant.core.doctor.causes import Occurrence, group
from assistant.core.doctor.changes import CONTEXT_ALERT
from assistant.core.doctor.clock import day_of
from assistant.core.doctor.context import CORE_TOOLS
from assistant.core.doctor.model import ThreadRef
from assistant.core.jobs import store as jobs
from assistant.core.jobs.store import Job, RunRecord
from assistant.core.logs import LOG_FILES
from assistant.core.memory import facts, profile
from tests.conftest import collect

OWNER = settings.owner_id
DAY = date(2026, 10, 24)
NEXT = DAY + timedelta(days=1)
HUB = "/home/me/lo9i/src/assistant/core/mcp/hub.py"


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), UTC)


def _record(at: datetime, level: str, logger: str, message: str) -> str:
    """As the daemon writes it: in the computer's own time."""
    local = at.astimezone()
    return f"{local:%Y-%m-%d %H:%M:%S},{local.microsecond // 1000:03d} {level} {logger}: {message}\n"


def _failed(at: datetime, error: str, path: str = HUB, function: str = "_connect") -> str:
    traceback = (
        "Couldn't connect to notes\nTraceback (most recent call last):\n"
        f'  File "{path}", line 120, in {function}\n'
        "    await self._open(server)\n"
        '  File "/home/me/lo9i/.venv/lib/python3.12/site-packages/httpx/_client.py", line 40, in send\n'
        "    raise error\n"
        f"{error}"
    )
    return _record(at, "ERROR", "assistant.core.mcp.hub", traceback)


def _write(name: str, *records: str) -> None:
    path = LOG_FILES[name].path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.writelines(records)


def _by_title(report) -> dict[str, Any]:
    return {c.title: c for c in report.causes}


async def test_the_days_log_records_are_grouped_by_cause(service):
    _write(
        "daemon",
        _failed(_at(DAY - timedelta(days=1), 23), "ConnectionError: attempt 9 failed"),
        _failed(_at(DAY, 9), "ConnectionError: attempt 1 failed"),
        _record(_at(DAY, 9, 30), "INFO", "assistant.daemon.server", "Daemon ready"),
        _failed(_at(DAY, 10), "ConnectionError: attempt 2 failed"),
        _record(_at(DAY, 10, 30), "WARNING", "assistant.core.channels.telegram", "Poll failed (retry 5)"),
        _failed(_at(DAY, 11), "ConnectionError: attempt 3 failed"),
    )
    # errors.log keeps the same errors: each counts once.
    _write("errors", _failed(_at(DAY, 11), "ConnectionError: attempt 3 failed"))
    report = await service.doctor.check(OWNER, DAY, whole_day=True)
    causes = _by_title(report)
    assert set(causes) == {"ConnectionError: attempt 3 failed", "Poll failed (retry 5)"}
    failing = causes["ConnectionError: attempt 3 failed"]
    assert (failing.count, failing.level, failing.where) == (3, "ERROR", "assistant/core/mcp/hub.py in _connect")
    assert failing.first == _at(DAY, 9).isoformat() and failing.last == _at(DAY, 11).isoformat()
    assert "Couldn't connect to notes" in failing.example
    polling = causes["Poll failed (retry 5)"]
    assert (polling.count, polling.level, polling.where) == (1, "WARNING", "assistant.core.channels.telegram")


async def test_a_cause_is_new_or_growing_against_the_day_before_and_gone_once_it_stops(service):
    _write(
        "daemon",
        _failed(_at(DAY, 9), "ConnectionError: refused"),
        _failed(_at(DAY, 10), "KeyError: 'title'", function="_render"),
        _failed(_at(NEXT, 9), "ConnectionError: refused"),
        _failed(_at(NEXT, 10), "ConnectionError: refused"),
        _failed(_at(NEXT, 11), "ConnectionError: refused"),
        _failed(_at(NEXT, 12), "TimeoutError: too slow", function="_call"),
    )
    first = await service.doctor.check(OWNER, DAY, whole_day=True)
    # Nothing to compare with: nothing is new.
    assert not any(c.change for c in first.causes) and await service.doctor.alerts(OWNER) == []
    report = await service.doctor.check(OWNER, NEXT, whole_day=True)
    causes = _by_title(report)
    assert report.compared_with == DAY.isoformat()
    assert (causes["ConnectionError: refused"].change, causes["ConnectionError: refused"].before) == ("growing", 1)
    assert causes["TimeoutError: too slow"].change == "new"
    assert [c.title for c in report.gone] == ["KeyError: 'title'"]
    alerts = [a for a in await service.alerts() if a.area == "doctor"]
    assert {(a.kind, a.title) for a in alerts} == {
        ("growing", "ConnectionError: refused"),
        ("new", "TimeoutError: too slow"),
    }
    told = (await notifications.recent(service.store, OWNER))[0]
    assert told.kind == "doctor" and not told.ok
    assert told.text.startswith("In the logs: 2 causes (1 new, 1 growing), 1 gone.")
    await service.dismiss_alert("doctor", causes["TimeoutError: too slow"].id)
    assert [a.title for a in await service.alerts() if a.area == "doctor"] == ["ConnectionError: refused"]


async def test_known_noise_is_left_out_until_it_is_forgotten(service):
    _write(
        "daemon",
        _record(_at(DAY, 9), "WARNING", "assistant.core.channels.telegram", "Poll failed (retry 1)"),
        _failed(_at(DAY, 10), "ConnectionError: refused"),
    )
    report = await service.doctor.check(OWNER, DAY, whole_day=True)
    noise = _by_title(report)["Poll failed (retry 1)"]
    assert not await service.mark_known(OWNER, "nothing-like-it")
    assert await service.mark_known(OWNER, noise.id)
    page = await service.doctor_page(OWNER)
    assert [k.title for k in page.known] == ["Poll failed (retry 1)"]
    assert page.report is not None and set(_by_title(page.report)) == {"ConnectionError: refused"}
    again = await service.doctor.check(OWNER, DAY, whole_day=True)
    assert set(_by_title(again)) == {"ConnectionError: refused"} and again.known == 1
    assert await service.forget_known(OWNER, noise.id) and not await service.forget_known(OWNER, noise.id)
    back = await service.doctor.check(OWNER, DAY, whole_day=True)
    assert "Poll failed (retry 1)" in _by_title(back) and back.known == 0


async def test_a_run_that_failed_and_a_call_left_without_a_result_are_found(service, script, monkeypatch):
    async def _locked(*args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(profile, "save", _locked)
    script.call("update_profile", section="goals", items=["run a marathon"]).reply("noted")
    session = await service.session(OWNER, "cli")
    await collect(service.send(session, "remember my goal"))
    today = day_of(datetime.now(UTC))
    report = await service.doctor.check(OWNER, today, whole_day=False)
    failed = [c for c in report.causes if c.kind == "conversation"]
    assert [(c.title, c.where, c.count) for c in failed] == [
        ("A run failed: OperationalError: database is locked", "tools", 1)
    ]
    assert [t.thread_id for t in failed[0].threads] == [session.thread_id]
    # A later run goes on from there; the failed one stays a failure, with its error, which the conversation marks.
    await collect(service.send(session, "did it save?"))
    report = await service.doctor.check(OWNER, today, whole_day=False)
    assert [(c.title, c.where) for c in report.causes if c.kind == "conversation"] == [
        ("A run failed: OperationalError: database is locked", "tools")
    ]


class _States:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages

    async def aget_state(self, config: Any, *, subgraphs: bool = False) -> StateSnapshot:
        return StateSnapshot({"messages": self._messages}, (), config, None, None, None, (), ())


def _said(at: datetime, text: str) -> HumanMessage:
    return HumanMessage([header_block("web", at), {"type": "text", "text": text}])


async def test_a_message_without_a_reply_counts_unless_a_run_is_still_on_it(service):
    now = _at(DAY, 12).isoformat()
    await conversations.save(service.store, OWNER, Conversation("t1", "Trip", now, now))
    states = _States(
        [
            _said(_at(DAY - timedelta(days=1), 20), "from the day before"),
            _said(_at(DAY, 9), "book the train"),
            _said(_at(DAY, 10), "and the hotel"),
            AIMessage("Booked."),
            _said(_at(DAY, 11), "and dinner"),
        ]
    )
    found = await conversation_causes.day_occurrences(service.store, states, OWNER, DAY, running={"t1"})
    [cause] = group("conversation", found)
    assert (cause.title, cause.count, cause.example) == (conversation_causes.NO_REPLY, 1, "book the train")
    assert cause.threads[0].title == "Trip"
    found = await conversation_causes.day_occurrences(service.store, states, OWNER, DAY, running=())
    assert group("conversation", found)[0].count == 2


async def test_a_scheduled_jobs_run_is_read_too_and_names_its_job(service):
    at = _at(DAY, 9)
    run = RunRecord(at.isoformat(), "failed", "", "job:daily-news:x")
    await jobs.save(service.store, Job("daily-news", OWNER, "0 9 * * *", "UTC", "news", "", runs=[run]))
    states = _States([_said(at, "Task: the news")])
    found = await conversation_causes.day_occurrences(service.store, states, OWNER, DAY, running=())
    [cause] = group("conversation", found)
    assert cause.threads == [
        ThreadRef(thread_id="job:daily-news:x", title="Job daily-news", job="daily-news", run_at=at.isoformat())
    ]


async def test_the_starting_context_is_measured_and_alerts_past_its_share_of_the_window(service, monkeypatch):
    first = await service.doctor.check(OWNER, DAY, whole_day=True)
    parts = {p.name: p for p in first.context.parts}
    assert parts[CORE_TOOLS].tokens > 0 and parts["Saved facts"].before is None
    assert first.context.tokens == sum(p.tokens for p in first.context.parts)
    assert not first.context.too_large
    monkeypatch.setattr(settings, "epoch_max_tokens", first.context.tokens * 2)
    for n in range(40):
        await facts.add(service.store, OWNER, f"The user's favourite thing number {n} is a long described thing.")
    report = await service.doctor.check(OWNER, NEXT, whole_day=True)
    grown = {p.name: p for p in report.context.parts}["Saved facts"]
    assert grown.before is not None and grown.tokens > grown.before
    assert report.context.too_large
    [alert] = [a for a in await service.alerts() if a.area == "doctor"]
    assert alert.name == CONTEXT_ALERT and alert.kind == "context"
    assert "Grew most since 2026-10-24: Saved facts +" in alert.error


async def test_the_daemon_checks_each_day_once_it_ended(service):
    now = _at(NEXT, 0, 1)
    await service.doctor.check(OWNER, DAY, whole_day=False)
    await service.doctor_schedule.tick(now)
    checked = (await service.doctor_page(OWNER)).report
    assert checked is not None and checked.day == DAY.isoformat() and checked.whole_day
    await service.doctor_schedule.tick(now + timedelta(hours=3))
    told = [n for n in await notifications.recent(service.store, OWNER) if n.kind == "doctor"]
    assert len(told) == 2 and told[0].title == "Health check of Sat 24 Oct"


async def test_a_daemon_down_for_days_checks_each_of_them_oldest_first(service):
    await service.doctor_schedule.tick(_at(NEXT, 0, 1))
    await service.doctor_schedule.tick(_at(NEXT + timedelta(days=3), 0, 1))
    reports = await records.reports(service.store, OWNER)
    days = [NEXT + timedelta(days=n) for n in range(3)]
    assert [r.day for r in reports] == [d.isoformat() for d in reversed([DAY, *days])]
    assert all(r.whole_day for r in reports) and reports[0].compared_with == days[1].isoformat()
    # Never further back than the reports kept.
    await service.doctor_schedule.tick(_at(NEXT + timedelta(days=30), 0, 1))
    reports = await records.reports(service.store, OWNER)
    assert len(reports) == records.KEPT_DAYS and reports[0].day == (NEXT + timedelta(days=29)).isoformat()


async def test_the_apps_check_today_in_the_background(service):
    page = await service.check_health(OWNER)
    assert page.checking
    await service.doctor.wait()
    page = await service.doctor_page(OWNER)
    assert not page.checking and page.report is not None
    assert page.report.day == day_of(datetime.now(UTC)).isoformat() and not page.report.whole_day


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("Task 4f3a9c21b7 failed after 3 tries", "Task 9e0b1c44aa failed after 5 tries", True),
        ("Couldn't reach notes", "Couldn't reach calendar", False),
    ],
)
def test_numbers_and_ids_dont_make_another_cause(first, second, same):
    occurrences = [Occurrence(first, "here", _at(DAY, 9)), Occurrence(second, "here", _at(DAY, 10))]
    assert (len(group("log", occurrences)) == 1) is same
