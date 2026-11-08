"""/subagents and the line under the title: the conversation's background subagents, or every conversation's, each
one's steps and answer, answering what one waits for, opening the conversation one works for, and a notice when one
waits for the user."""

from datetime import UTC, datetime
from types import SimpleNamespace

from textual.widgets import Button, OptionList, Static

from lo9i.core.agent import BackgroundStep, BackgroundSubagent, Conversation, Session
from lo9i.core.background_subagents.records import Status
from lo9i.core.config import settings
from lo9i.core.events import ApprovalRequired
from lo9i_terminal.repl import Repl
from lo9i_terminal.subagents_text import (
    context_line,
    conversation_titles,
    elapsed,
    running_line,
    subagent_detail,
    subagent_line,
)
from lo9i_terminal.tui.screens import ApprovalScreen, SubagentsScreen
from tests.terminal.conftest import FakeConversations, FakeSubagents, wait_for

_NOW = datetime(2026, 11, 1, 10, 5, tzinfo=UTC)


def _subagent(thread_id: str, status: Status = "running", **fields) -> BackgroundSubagent:
    values = {"step": "bash ls", "steps": 1, "result": "", "ended_at": "", "waiting": []} | fields
    return BackgroundSubagent(
        "s1",
        "owner",
        thread_id,
        "cli",
        "Find the cheapest flight",
        "",
        [],
        "2026-11-01T10:00:00+00:00",
        status,
        **values,
    )


def test_a_line_says_its_status_how_long_and_its_task():
    assert subagent_line(_subagent("t1"), _NOW) == "… working · 5m · Find the cheapest flight"
    ended = _subagent("t1", "done", ended_at="2026-11-01T10:00:42+00:00")
    assert elapsed(ended, _NOW) == "42s"
    assert running_line([_subagent("t1"), _subagent("t1", "waiting"), ended]) == (
        "2 subagents working (/subagents), 1 waiting for you"
    )
    assert running_line([ended]) == ""


def test_its_detail_says_its_context_and_model_calls_and_when_each_step_was_asked_for(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "UTC")
    subagent = _subagent("t1", model_calls=3, context_tokens=12_000, context_limit=200_000)
    assert context_line(subagent) == "Context: 6% · 12k / 200k tokens · Model calls: 3"
    assert context_line(_subagent("t1")) == "Context: \u2013 · Model calls: 0"
    step = BackgroundStep(0, "c1", "bash", {"command": "ls"}, "a\n", True, at="2026-11-01T10:01:00+00:00")
    assert "✓ 10:01 bash ls" in subagent_detail(subagent, [step], _NOW)
    assert "✓ 01 Nov 10:01 bash ls" in subagent_detail(subagent, [step], datetime(2026, 11, 2, tzinfo=UTC))


async def test_subagents_show_with_their_steps_and_what_they_wait_for_is_answered(app, client):
    async with app.run_test(size=(140, 40)) as pilot:
        thread_id = app._live.session.thread_id
        asked = ApprovalRequired("i1", {"tool": "bash", "command": "rm -rf build", "reason": "deletes files"})
        client.subagents.items = [_subagent(thread_id, "waiting", waiting=[asked])]
        client.subagents.steps["s1"] = [BackgroundStep(0, "c1", "bash", {"command": "ls"}, "a\n", True)]
        await client.bus.put(("subagents", {"id": "s1", "thread_id": thread_id, "status": "waiting"}))
        await wait_for(pilot, lambda: "a subagent working (/subagents), 1 waiting for you" in app.sub_title)
        await pilot.click("#prompt")
        await pilot.press(*"/subagents", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, SubagentsScreen))
        screen = app.screen
        detail = screen.query_one("#subagents-detail", Static)
        await wait_for(pilot, lambda: "✓ bash ls" in str(detail.render()))
        options = screen.query_one("#subagents-list", OptionList)
        assert "waiting for your answer" in str(options.get_option_at_index(0).prompt)
        screen.query_one("#answer", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.subagents.answers == [("s1", "i1", {"approved": True, "reason": None})])
        assert not screen.query_one("#remove", Button).display
        screen.query_one("#stop", Button).press()
        await wait_for(pilot, lambda: client.subagents.stopped == ["s1"])


def test_a_line_names_the_conversation_it_works_for_when_given():
    assert subagent_line(_subagent("t1"), _NOW, conversation="plan my trip") == (
        "… working · 5m · plan my trip: Find the cheapest flight"
    )
    titles = conversation_titles(
        [_subagent("owner:abc"), _subagent("gone")], [Conversation("owner:abc", "trip", "", "")]
    )
    assert titles == {"owner:abc": "trip", "gone": "Untitled"}


async def test_every_conversations_subagents_show_with_their_conversation_and_open_it(app, client):
    async with app.run_test(size=(140, 40)) as pilot:
        client.conversations.items.append(Conversation("owner:taxes", "file my taxes", "", ""))
        client.subagents.items = [_subagent("owner:taxes")]
        await pilot.click("#prompt")
        await pilot.press(*"/subagents all", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, SubagentsScreen))
        screen = app.screen
        options = screen.query_one("#subagents-list", OptionList)
        await wait_for(pilot, lambda: options.option_count == 1)
        assert "file my taxes: Find the cheapest flight" in str(options.get_option_at_index(0).prompt)
        screen.query_one("#scope", Button).press()
        await wait_for(pilot, lambda: screen.query_one("#subagents").has_class("empty"))
        screen.query_one("#scope", Button).press()
        await wait_for(pilot, lambda: options.option_count == 1 and screen.query_one("#open-conversation").display)
        screen.query_one("#open-conversation", Button).press()
        await wait_for(pilot, lambda: client.active_thread == "owner:taxes")


async def test_the_plain_repl_lists_every_conversations_subagents_after_their_conversation(capsys):
    subagents, conversations = FakeSubagents(), FakeConversations()
    subagents.items = [_subagent("owner:abc"), _subagent("cli:here")]
    service = SimpleNamespace(subagents=subagents, conversations=conversations)
    repl = Repl(service, Session("owner", "cli", "cli:here"))  # type: ignore[arg-type]
    await repl._subagents("all")
    shown = capsys.readouterr().out
    assert "1. " in shown and "plan my trip: Find the cheapest flight" in shown
    await repl._subagents("")
    assert "plan my trip" not in capsys.readouterr().out
    await repl._subagents("all 1")
    assert "Find the cheapest flight" in capsys.readouterr().out
