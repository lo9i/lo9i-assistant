"""/subagents and the line under the title: the conversation's background subagents, each one's steps and answer,
answering what one waits for, and a notice when one waits for the user."""

from datetime import UTC, datetime

from textual.widgets import Button, OptionList, Static

from assistant.core.agent import BackgroundStep, BackgroundSubagent
from assistant.core.background_subagents.records import Status
from assistant.core.events import ApprovalRequired
from assistant_terminal.subagents_text import elapsed, running_line, subagent_line
from assistant_terminal.tui.screens import ApprovalScreen, SubagentsScreen
from tests.terminal.conftest import wait_for

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
