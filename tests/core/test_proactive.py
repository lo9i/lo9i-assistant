"""The assistant's own initiative (core/proactive/): open loops, the morning briefing and its schedule, the nightly and
weekly reviews, reminders, muted kinds of suggestion, and open loops kept from conversations' archived parts. A plugin
listing its day runs in-process (core/mcp/today.py); the mail picks and the reviews are the `drafts` fakes."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from lo9i.core import conversations, notifications
from lo9i.core.agent import AssistantService, McpServer, Session
from lo9i.core.config import settings
from lo9i.core.conversation.digest import MemoryDigest
from lo9i.core.jobs import store as jobs
from lo9i.core.jobs.store import Job, RunRecord
from lo9i.core.mcp import hub as hub_module
from lo9i.core.mcp import servers
from lo9i.core.memory import facts
from lo9i.core.proactive import loops, records
from lo9i.core.proactive.mail import Unread, UnreadMail
from lo9i.core.proactive.model import LoopDraft, MailDraft, MailPick, ProactiveSettings, ReviewDraft, Suggestion
from lo9i.core.proactive.reminders import PER_DAY
from tests.conftest import collect

# A Sunday.
SUNDAY = datetime(2026, 11, 1, tzinfo=UTC)
DENTIST = {"title": "Dentist", "subtitle": "Clinic", "time": "10:00", "kind": "calendar", "key": "event 1"}
BILL = {
    "title": "Electricity",
    "subtitle": "$ 61,000",
    "date": "2026-11-03",
    "needs": "Pay the electricity bill",
    "kind": "bill due",
    "key": "bill 7",
}


class _Planner:
    """What the plugin lists for a day, and the days and languages it was asked for; `failing` has it answer an
    error."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = [DENTIST, BILL]
        self.asked: list[tuple[str, str]] = []
        self.failing = False

    def server(self) -> MCPServer:
        server = MCPServer("planner")

        @server.tool(annotations=ToolAnnotations(read_only_hint=True))
        def today(day: str, language: str) -> dict:
            """The day."""
            self.asked.append((day, language))
            if self.failing:
                raise ToolError("the database is locked")
            return {"heading": "Planner", "items": self.items, "note": ""}

        @server.tool(annotations=ToolAnnotations(read_only_hint=True))
        def list_events() -> str:
            """Today's events."""
            return "Dentist at 10:00"

        return server


class _Chat:
    """A chat channel that takes every message."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> list[str]:
        self.sent.append(text)
        return [str(len(self.sent))]


@pytest.fixture
def planner() -> _Planner:
    return _Planner()


@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> list[Unread]:
    """The unread mail every account has: none unless a test adds some."""
    unread: list[Unread] = []

    async def since(self: UnreadMail, day: date) -> list[Unread]:
        return list(unread)

    monkeypatch.setattr(UnreadMail, "since", since)
    return unread


@pytest.fixture
async def service(
    script, digests, summaries, titles, drafts, planner, inbox, monkeypatch
) -> AsyncIterator[AssistantService]:
    """The service with its MCP hub running; every server is the in-process planner."""
    fake = planner.server()
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


async def _install_planner(service: AssistantService) -> None:
    await servers.save(service.store, McpServer(name="planner", command="planner-mcp", today_tool="today"))
    await service.mcp.reload()
    for _ in range(100):
        if service.mcp.state("planner")[0] == "connected":
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the planner never connected")


async def _run(service: AssistantService, work: Any, now: datetime) -> None:
    service.proactive_runs.start(work, now)
    await service.proactive_runs.wait()


async def _tick(service: AssistantService, now: datetime) -> None:
    await service.proactive_schedule.tick(now)
    await service.proactive_runs.wait()


async def _told(service: AssistantService) -> str:
    briefing = await records.latest_briefing(service.store, "owner")
    assert briefing is not None
    return briefing.text


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


@pytest.mark.usefixtures("feed_keeps_every_kind")
async def test_the_briefing_lays_out_the_plugins_lists_without_the_model(service, script, drafts, planner, chat):
    await _install_planner(service)
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert planner.asked == [("2026-11-01", "en")] and script.requests == [] and drafts.mail.requests == []
    text = "Planner\n- 10:00 Dentist · Clinic\n- Tue 03 Nov Electricity · $ 61,000 → Pay the electricity bill"
    assert chat.sent == [text] and await _told(service) == text
    [told] = await notifications.recent(service.store, "owner")
    assert (told.kind, told.title, told.text) == ("briefing", "Morning briefing", text)
    [loop] = await loops.open_loops(service.store, "owner")
    assert (loop.text, loop.kind, loop.due, loop.plugin) == (
        "Pay the electricity bill",
        "bill due",
        "2026-11-03",
        "planner",
    )


async def test_a_loop_from_a_plugins_list_closes_when_the_list_no_longer_has_it(service, planner):
    await _install_planner(service)
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    assert [o.text for o in await loops.open_loops(service.store, "owner")] == ["Pay the electricity bill"]
    planner.items = [DENTIST]
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=2))
    assert await loops.open_loops(service.store, "owner") == []
    [paid] = await loops.all_loops(service.store, "owner")
    assert paid.status == "done"


async def test_a_list_that_cant_be_read_says_so_and_closes_nothing(service, planner):
    await _install_planner(service)
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    planner.failing = True
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    assert "Couldn't read\n- planner: planner couldn't list its day:" in await _told(service)
    assert "the database is locked" in await _told(service)
    assert [o.text for o in await loops.open_loops(service.store, "owner")] == ["Pay the electricity bill"]


async def test_nothing_is_sent_when_there_is_nothing_to_tell(service, script, drafts, chat):
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert script.requests == [] and drafts.mail.requests == []
    assert chat.sent == [] and await notifications.recent(service.store, "owner") == []
    briefing = await records.latest_briefing(service.store, "owner")
    assert briefing is not None and briefing.status == "nothing"


async def test_items_and_loops_of_a_muted_kind_are_left_out(service, planner):
    await _install_planner(service)
    await loops.add(service.store, "owner", LoopDraft(text="Answer Ana", kind="unanswered mail"), "briefing")
    await loops.add(service.store, "owner", LoopDraft(text="Renew passport", due="2026-11-20"), "assistant")
    await records.mute(service.store, "owner", "unanswered mail")
    await records.mute(service.store, "owner", "bill due")
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    text = await _told(service)
    assert text == "Planner\n- 10:00 Dentist · Clinic\n\nOpen loops\n- Renew passport (due Fri 20 Nov)"


async def test_the_briefing_is_in_the_language_chosen(service, planner):
    await service.set_language("es")
    await loops.add(service.store, "owner", LoopDraft(text="Renovar el pasaporte"), "assistant")
    await _install_planner(service)
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert planner.asked == [("2026-11-01", "es")]
    assert "mar 03 nov Electricity" in await _told(service)
    assert "Pendientes\n- Renovar el pasaporte" in await _told(service)


async def test_the_mail_that_matters_is_picked_by_one_model_call(service, drafts, inbox, chat):
    inbox.append(Unread("Work", 5, "Ana <ana@x.com>", "Friday?", "2026-10-29T09:00:00+00:00"))
    inbox.append(Unread("Work", 6, "News <n@x.com>", "Weekly digest", "2026-10-31T09:00:00+00:00"))
    picks = [MailPick(account="Work", uid=5, line="Ana asks if Friday works", asks=True)]
    drafts.mail.answers.append(MailDraft(important=[*picks, MailPick(account="Work", uid=99, line="x", asks=False)]))
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert "[Work 5]" in drafts.mail.requests[0][-1].text and "Weekly digest" in drafts.mail.requests[0][-1].text
    assert chat.sent == ["Mail\n- Ana asks if Friday works"]
    [loop] = await loops.open_loops(service.store, "owner")
    assert (loop.text, loop.kind, loop.key) == ("Ana asks if Friday works", "unanswered mail", "mail work 5")


async def test_mail_isnt_read_by_the_model_when_its_muted(service, drafts, inbox):
    inbox.append(Unread("Work", 5, "Ana <ana@x.com>", "Friday?", "2026-10-29T09:00:00+00:00"))
    await records.mute(service.store, "owner", "important mail")
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    assert drafts.mail.requests == []


async def test_a_failed_briefing_is_recorded(service, drafts, inbox):
    inbox.append(Unread("Work", 5, "Ana <ana@x.com>", "Friday?", "2026-10-29T09:00:00+00:00"))
    drafts.mail.answers.append(RuntimeError("the model is down"))
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    briefing = await records.latest_briefing(service.store, "owner")
    assert briefing is not None and briefing.status == "failed" and "the model is down" in briefing.error


async def test_a_failed_briefing_or_review_is_an_alert_until_dismissed_or_the_next_one_works(service, drafts, inbox):
    inbox.append(Unread("Work", 5, "Ana <ana@x.com>", "Friday?", "2026-10-29T09:00:00+00:00"))
    drafts.mail.answers.append(RuntimeError("the model is down"))
    drafts.review.answers.append(RuntimeError("the model is down"))
    await _run(service, "briefing", SUNDAY.replace(hour=8))
    await _run(service, "nightly", SUNDAY.replace(hour=23))
    alerts = [a for a in await service.alerts() if a.area == "proactive"]
    assert sorted(a.name for a in alerts) == ["briefing", "nightly"]
    assert all("the model is down" in a.error for a in alerts)
    await service.dismiss_alert("proactive", "briefing")
    assert [a.name for a in await service.alerts() if a.area == "proactive"] == ["nightly"]
    drafts.review.answers.append(ReviewDraft(summary="Quiet day."))
    await _run(service, "nightly", SUNDAY.replace(hour=23) + timedelta(days=1))
    assert [a for a in await service.alerts() if a.area == "proactive"] == []


# The reviews.


async def test_the_nightly_review_keeps_loops_habits_and_suggestions_for_the_next_briefing(
    service, drafts, planner, inbox, chat
):
    await _install_planner(service)
    inbox.append(Unread("Work", 5, "Ana <ana@x.com>", "Friday?", "2026-11-01T09:00:00+00:00"))
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
    assert "Planner\n- 10:00 Dentist · Clinic" in read and "[Work 5]" in read and "Friday?" in read
    assert [o.text for o in await loops.open_loops(service.store, "owner")] == ["Book the flight"]
    assert [f.text for f in await facts.load_all(service.store, "owner")] == [
        "Habit: Issues invoices on the 1st of each month"
    ]
    [review] = await records.reviews(service.store, "owner")
    assert [s.text for s in review.suggestions] == ["Add the flight to the calendar?"] and not review.briefed
    assert (review.added, review.closed) == (1, 1)
    inbox.clear()
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    assert "Suggestions\n- Add the flight to the calendar?" in await _told(service)
    assert (await records.reviews(service.store, "owner"))[0].briefed


async def test_the_weekly_review_reads_the_weeks_nightly_ones_and_feeds_the_monday_briefing(service, drafts):
    drafts.review.answers.append(ReviewDraft(summary="Quiet day."))
    await _run(service, "nightly", SUNDAY.replace(hour=23))
    drafts.review.answers.append(ReviewDraft(summary="A week of invoices."))
    await _run(service, "weekly", SUNDAY.replace(hour=23, minute=5))
    assert "2026-11-01: Quiet day." in drafts.review.requests[1][-1].text
    await _run(service, "briefing", SUNDAY.replace(hour=8) + timedelta(days=1))
    assert await _told(service) == "Last week\n- A week of invoices."


# Reminders.


async def test_reminders_go_at_their_time_within_the_day_a_few_a_day(service, chat):
    for n in range(PER_DAY + 1):
        await loops.add(service.store, "owner", LoopDraft(text=f"Call {n}", remind_at="2026-11-02T09:00"), "assistant")
    await loops.add(
        service.store, "owner", LoopDraft(text="Muted", kind="bill due", remind_at="2026-11-02T09:00"), "assistant"
    )
    await records.save_settings(service.store, "owner", ProactiveSettings(briefing=False))
    await records.mute(service.store, "owner", "bill due")
    monday = SUNDAY + timedelta(days=1)
    await _tick(service, monday.replace(hour=8, minute=59))
    await _tick(service, monday.replace(hour=23, minute=30))
    assert chat.sent == []
    await _tick(service, monday.replace(hour=9, minute=1))
    assert len(chat.sent) == PER_DAY and all(s.startswith("Reminder: Call") for s in chat.sent)
    await _tick(service, monday.replace(hour=8, minute=1) + timedelta(days=1))
    assert len(chat.sent) == PER_DAY + 1 and not any("Muted" in s for s in chat.sent)


async def test_a_reminder_opens_the_conversation_its_loop_came_from(service):
    draft = LoopDraft(text="Call the bank", remind_at="2026-11-02T09:00")
    await loops.add(service.store, "owner", draft, "conversation", thread_id="t1")
    await records.save_settings(service.store, "owner", ProactiveSettings(briefing=False))
    await _tick(service, SUNDAY.replace(hour=9, minute=1) + timedelta(days=1))
    [told] = [n for n in await notifications.recent(service.store, "owner") if n.kind == "reminder"]
    assert told.thread_id == "t1"


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
