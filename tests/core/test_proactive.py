"""The assistant's own initiative (core/proactive/): open loops, the morning briefing and its schedule, the nightly and
weekly reviews, reminders, muted kinds of suggestion, and open loops kept from conversations' archived parts. The
calendar plugin runs in-process; the writers are the `drafts` fakes."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from assistant.core import conversations, notifications
from assistant.core.agent import AssistantService, McpServer, Session
from assistant.core.config import settings
from assistant.core.conversation.digest import MemoryDigest
from assistant.core.integrations.email import accounts as email_accounts
from assistant.core.integrations.email.accounts import EmailConfig
from assistant.core.jobs import store as jobs
from assistant.core.jobs.store import Job, RunRecord
from assistant.core.mcp import hub as hub_module
from assistant.core.mcp import servers
from assistant.core.memory import facts
from assistant.core.proactive import loops, records, sources
from assistant.core.proactive.model import BriefingDraft, LoopDraft, ProactiveSettings, ReviewDraft, Suggestion
from assistant.core.proactive.reminders import PER_DAY
from tests.conftest import collect

LIST = "mcp__calendar__list_events"
CREATE = "mcp__calendar__create_event"
# A Sunday.
SUNDAY = datetime(2026, 11, 1, tzinfo=UTC)


def _calendar() -> MCPServer:
    server = MCPServer("calendar")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_events() -> str:
        """Today's events."""
        return "Dentist at 10:00"

    @server.tool()
    def create_event(title: str) -> str:
        """Add an event."""
        return f"created {title}"

    return server


class _Chat:
    """A chat channel that takes every message."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> list[str]:
        self.sent.append(text)
        return [str(len(self.sent))]


@pytest.fixture
async def service(script, digests, summaries, titles, drafts, monkeypatch) -> AsyncIterator[AssistantService]:
    """The service with its MCP hub running; every server is the in-process calendar."""
    fake = _calendar()
    monkeypatch.setattr(
        hub_module,
        "open_client",
        lambda server, handler, auth, extensions, in_flight=None: Client(
            fake, message_handler=handler, extensions=extensions
        ),
    )
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        yield svc
        stop.set()
        await task


@pytest.fixture
def chat(service: AssistantService) -> _Chat:
    chat = _Chat()
    service.outbox.register("telegram", chat)
    return chat


async def _install_calendar(service: AssistantService) -> None:
    await servers.save(service.store, McpServer(name="calendar", command="calendar-mcp", trusted=True))
    await service.mcp.reload()
    for _ in range(100):
        if service.mcp.state("calendar")[0] == "connected":
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the calendar never connected")


async def _run(service: AssistantService, work: Any, now: datetime) -> None:
    service.proactive_runs.start(work, now)
    await service.proactive_runs.wait()


async def _tick(service: AssistantService, now: datetime) -> None:
    await service.proactive_schedule.tick(now)
    await service.proactive_runs.wait()


def _bound_names(tools: list[Any]) -> set[str]:
    return {t["function"]["name"] for t in tools}


# Open loops.


async def test_a_loop_is_added_once_per_key_and_one_closed_doesnt_come_back(service):
    first = await loops.add(service.store, "owner", LoopDraft(text="Pay the  electricity bill"), "assistant")
    assert first is not None and first.text == "Pay the electricity bill" and first.status == "open"
    assert await loops.add(service.store, "owner", LoopDraft(text="pay the electricity bill!"), "review") is None
    await loops.close(service.store, "owner", first.id, "dismissed")
    assert await loops.add(service.store, "owner", LoopDraft(text="Pay the electricity bill"), "briefing") is None
    keyed = LoopDraft(text="Electricity due Thursday", key="electricity bill 2026-11")
    assert await loops.add(service.store, "owner", keyed, "briefing") is not None
    assert [o.text for o in await loops.open_loops(service.store, "owner")] == ["Electricity due Thursday"]


async def test_a_reminder_time_is_read_in_the_users_time_zone(service, monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Argentina/Buenos_Aires")
    draft = LoopDraft(text="Call the bank", remind_at="2026-11-03T10:00")
    loop = await loops.add(service.store, "owner", draft, "assistant")
    assert loop is not None and loop.remind_at == "2026-11-03T13:00:00+00:00"


async def test_settings_are_on_by_default_and_a_kind_is_muted_once(service):
    chosen = await records.load_settings(service.store, "owner")
    assert chosen.briefing and chosen.nightly and chosen.weekly and chosen.reminders
    assert (chosen.briefing_time, chosen.nightly_time, chosen.weekly_day) == ("08:00", "23:00", 6)
    await records.mute(service.store, "owner", "Automation  suggestion")
    chosen = await records.mute(service.store, "owner", "automation suggestion")
    assert chosen.muted == ["automation suggestion"]
    assert (await records.mute(service.store, "owner", "automation suggestion", muted=False)).muted == []
    with pytest.raises(ValueError):
        ProactiveSettings(briefing_time="8am")


# The schedule.


async def test_the_briefing_is_due_at_its_time_once_a_day_and_not_hours_late(service):
    day = SUNDAY + timedelta(days=1)
    await _tick(service, day.replace(hour=7, minute=59))
    assert await records.latest_briefing(service.store, "owner") is None
    await _tick(service, day.replace(hour=8))
    first = await records.latest_briefing(service.store, "owner")
    assert first is not None and first.day == "2026-11-02" and first.status == "nothing"
    await _tick(service, day.replace(hour=9))
    assert await records.latest_briefing(service.store, "owner") == first
    await _tick(service, day.replace(hour=15) + timedelta(days=1))
    assert await records.latest_briefing(service.store, "owner") == first


async def test_a_briefing_turned_off_isnt_sent(service):
    await records.save_settings(service.store, "owner", ProactiveSettings(briefing=False))
    await _tick(service, SUNDAY.replace(hour=8))
    assert await records.latest_briefing(service.store, "owner") is None


async def test_the_nightly_review_comes_at_its_time_and_the_weekly_after_it_on_its_day(service):
    await _tick(service, SUNDAY.replace(hour=22, minute=59))
    assert await records.reviews(service.store, "owner") == []
    await _tick(service, SUNDAY.replace(hour=23))
    assert [r.kind for r in await records.reviews(service.store, "owner")] == ["nightly"]
    await _tick(service, SUNDAY.replace(hour=23, minute=1))
    assert [r.kind for r in await records.reviews(service.store, "owner")] == ["weekly", "nightly"]
    await _tick(service, SUNDAY.replace(hour=23, minute=2) + timedelta(days=1))
    assert [r.kind for r in await records.reviews(service.store, "owner")] == ["nightly", "weekly", "nightly"]


# The briefing.


async def test_the_briefing_reads_the_calendar_and_tells_what_it_wrote(service, script, drafts, chat):
    await _install_calendar(service)
    script.call(LIST).reply("Dentist today 10:00.")
    reminder = LoopDraft(text="Gas bill due Thursday", kind="bill due", key="gas 2026-11", due="2026-11-05")
    drafts.briefing.answers.append(BriefingDraft(text="Today: dentist at 10:00.", reminders=[reminder]))
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert _bound_names(script.bound[0]) == {LIST}
    assert "Calendar: today's events" in script.requests[0][-1].text
    assert "Dentist today 10:00." in drafts.briefing.requests[0][-1].text
    briefing = await records.latest_briefing(service.store, "owner")
    assert briefing is not None and briefing.status == "sent" and briefing.channels == ["telegram"]
    assert chat.sent == ["Today: dentist at 10:00."]
    [told] = await notifications.recent(service.store, "owner")
    assert (told.kind, told.title, told.text) == ("briefing", "Morning briefing", "Today: dentist at 10:00.")
    [loop] = await loops.open_loops(service.store, "owner")
    assert (loop.text, loop.source, loop.due, loop.kind) == (
        "Gas bill due Thursday",
        "briefing",
        "2026-11-05",
        "bill due",
    )


async def test_nothing_is_written_when_there_is_nothing_to_tell(service, script, drafts, chat):
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert script.requests == [] and drafts.briefing.requests == []
    assert chat.sent == [] and await notifications.recent(service.store, "owner") == []


async def test_open_loops_of_a_muted_kind_are_left_out(service, drafts):
    await loops.add(service.store, "owner", LoopDraft(text="Answer Ana", kind="unanswered mail"), "briefing")
    await loops.add(service.store, "owner", LoopDraft(text="Renew passport"), "assistant")
    await records.mute(service.store, "owner", "unanswered mail")
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    written = drafts.briefing.requests[0][-1].text
    assert "Renew passport" in written and "Answer Ana" not in written and "unanswered mail" in written


async def test_a_failed_briefing_is_recorded(service, drafts):
    await loops.add(service.store, "owner", LoopDraft(text="Renew passport"), "assistant")
    drafts.briefing.answers.append(RuntimeError("the model is down"))
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    briefing = await records.latest_briefing(service.store, "owner")
    assert briefing is not None and briefing.status == "failed" and "the model is down" in briefing.error


# The reviews.


async def test_the_nightly_review_keeps_loops_habits_and_suggestions_for_the_next_briefing(service, drafts, chat):
    at = SUNDAY.replace(hour=12).isoformat()
    await conversations.save(service.store, "owner", conversations.Conversation("t1", "Invoices", at, at))
    job = Job("backup", "owner", "0 3 * * *", "UTC", "back up", "", runs=[RunRecord(at, "failed", "disk full")])
    await jobs.save(service.store, job)
    done = await loops.add(service.store, "owner", LoopDraft(text="Send the contract"), "assistant")
    assert done is not None
    drafts.review.answers.append(
        ReviewDraft(
            summary="Talked about invoices.",
            new_loops=[LoopDraft(text="Book the flight", kind="recurring task")],
            done_loop_ids=[done.id, "unknown"],
            habits=["Issues invoices on the 1st of each month", "issues invoices on the 1st of each month"],
            suggestions=[
                Suggestion(kind="automation suggestion", text="Schedule the invoices as a job?"),
                Suggestion(kind="missing calendar entry", text="Add the flight to the calendar?"),
            ],
        )
    )
    await records.mute(service.store, "owner", "automation suggestion")
    await _run(service, "nightly", SUNDAY.replace(hour=23))
    read = drafts.review.requests[0][-1].text
    assert "## Invoices" in read and "backup" in read and "disk full" in read and "Send the contract" in read
    assert [o.text for o in await loops.open_loops(service.store, "owner")] == ["Book the flight"]
    assert [f.text for f in await facts.load_all(service.store, "owner")] == [
        "Habit: Issues invoices on the 1st of each month"
    ]
    [review] = await records.reviews(service.store, "owner")
    assert [s.text for s in review.suggestions] == ["Add the flight to the calendar?"] and not review.briefed
    assert (review.added, review.closed) == (1, 1)
    drafts.briefing.answers.append(BriefingDraft(text="Add the flight to the calendar?"))
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    written = drafts.briefing.requests[0][-1].text
    assert "Add the flight to the calendar?" in written and "Issues invoices on the 1st" in written
    assert (await records.reviews(service.store, "owner"))[0].briefed
    assert chat.sent == ["Add the flight to the calendar?"]


async def test_the_weekly_review_reads_the_weeks_nightly_ones_and_feeds_the_monday_briefing(service, drafts):
    drafts.review.answers.append(ReviewDraft(summary="Quiet day."))
    await _run(service, "nightly", SUNDAY.replace(hour=23))
    drafts.review.answers.append(ReviewDraft(summary="A week of invoices."))
    await _run(service, "weekly", SUNDAY.replace(hour=23, minute=5))
    assert "2026-11-01: Quiet day." in drafts.review.requests[1][-1].text
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    assert "# Last week\n- A week of invoices." in drafts.briefing.requests[0][-1].text


# Reminders.


async def test_reminders_go_at_their_time_within_the_day_a_few_a_day(service, chat):
    for n in range(PER_DAY + 1):
        await loops.add(service.store, "owner", LoopDraft(text=f"Call {n}", remind_at="2026-11-02T09:00"), "assistant")
    await loops.add(
        service.store, "owner", LoopDraft(text="Muted", kind="bill due", remind_at="2026-11-02T09:00"), "assistant"
    )
    await records.mute(service.store, "owner", "bill due")
    monday = SUNDAY + timedelta(days=1)
    await _tick(service, monday.replace(hour=8, minute=59))
    await _tick(service, monday.replace(hour=23, minute=30))
    assert chat.sent == []
    await _tick(service, monday.replace(hour=9, minute=1))
    assert len(chat.sent) == PER_DAY and all(s.startswith("Reminder: Call") for s in chat.sent)
    await _tick(service, monday.replace(hour=8, minute=1) + timedelta(days=1))
    assert len(chat.sent) == PER_DAY + 1 and not any("Muted" in s for s in chat.sent)


# Conversations and the assistant's tools.


async def test_what_a_conversation_leaves_open_becomes_a_loop_and_what_it_shows_done_closes(service, digests):
    done = await loops.add(service.store, "u", LoopDraft(text="Send the contract"), "assistant")
    assert done is not None
    digests.result = lambda data: MemoryDigest(
        episode_summary="e",
        profile=data.profile,
        new_facts=[],
        outdated_fact_ids=[],
        open_items=[LoopDraft(text="Wait for Ana's answer", due="2026-11-10")],
        done_loop_ids=[loop.id for loop in data.open_loops],
    )
    session = Session("u", "telegram", await service.new_thread("u"))
    for text in ["I sent the contract", "now I wait for Ana"]:
        await collect(service.send(session, text))
    await service.channel_wrote("u", "telegram", session.thread_id)
    await service.channel_wrote("u", "telegram", await service.new_thread("u"))
    await asyncio.gather(*service._background)
    await service.memory_writer.write_all()
    assert [o.text for o in digests.inputs[0].open_loops] == ["Send the contract"]
    [left] = await loops.open_loops(service.store, "u")
    assert (left.text, left.source, left.thread_id) == ("Wait for Ana's answer", "conversation", session.thread_id)


async def test_closing_a_loop_from_a_conversation_can_mute_its_kind(service, script):
    loop = await loops.add(service.store, "owner", LoopDraft(text="Answer Ana", kind="unanswered mail"), "briefing")
    assert loop is not None
    script.call("close_open_loop", loop_id=loop.id, status="dismissed", stop_suggesting=True).reply("Done.")
    await collect(service.send(await service.session("owner", "cli"), "less of this"))
    assert (await loops.get(service.store, "owner", loop.id)).status == "dismissed"  # type: ignore[union-attr]
    assert (await records.load_settings(service.store, "owner")).muted == ["unanswered mail"]


async def test_the_page_closes_and_opens_loops_again(service):
    loop = await loops.add(service.store, "owner", LoopDraft(text="Renew passport", kind="recurring task"), "review")
    assert loop is not None
    page = await service.close_loop("owner", loop.id, "done", stop_suggesting=True)
    assert page.loops[0].status == "done" and page.settings.muted == ["recurring task"]
    page = await service.close_loop("owner", loop.id, "open")
    assert page.loops[0].status == "open" and page.loops[0].closed_at == ""


class _Tools:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def read_only_definitions(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": n}} for n in self._names]

    def plugin_of(self, name: str) -> str | None:
        return name.split("__")[1]


async def test_only_the_days_plugins_and_readable_mail_are_asked(service, monkeypatch):
    tools = _Tools(["mcp__calendar__list_events", "mcp__watchlist__list_titles", "mcp__billing__prepare_month"])
    found = await sources.available(service.store, tools)
    assert found.names == ["billing", "calendar"] and len(found.tools) == 2
    readable = EmailConfig(host="smtp", sender="me@x.com", imap_host="imap", label="Work")

    async def accounts(store: Any) -> list[EmailConfig]:
        return [readable, EmailConfig(host="smtp", sender="out@x.com", label="Send only")]

    monkeypatch.setattr(email_accounts, "list_accounts", accounts)
    found = await sources.available(service.store, tools)
    assert found.names == ["billing", "calendar", "mail"] and found.accounts == ["Work <me@x.com>"]
    assert _bound_names(found.tools) == {"mcp__calendar__list_events", "mcp__billing__prepare_month", "search_email"}
    asked = sources.asked(found, {"billing": "B", "calendar": "C", "mail": "M in {accounts}"})
    assert asked == "- B\n- C\n- M in Work <me@x.com>"
