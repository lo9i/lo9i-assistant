"""The open conversations (Ctrl+O, /open): the ones shown in this app, and any other with something working in it,
to switch between, as the web app's sidebar lists them under Chat."""

from textual.widgets import Button, OptionList

from assistant.core.agent import Conversation, RunningTask
from assistant.core.events import ApprovalRequired
from assistant_terminal.open_text import OpenItem, line, open_list
from assistant_terminal.tui.screens import ConversationsScreen, OpenConversationsScreen
from tests.terminal.conftest import wait_for

_WHEN = "2026-10-29T10:00:00+00:00"


def _conversation(thread_id: str, title: str, inbox: bool = False) -> Conversation:
    return Conversation(thread_id, title, _WHEN, _WHEN, inbox=inbox)


async def _opened(pilot, app) -> OpenConversationsScreen:
    """The screen once it's shown with its list."""
    await wait_for(pilot, lambda: isinstance(app.screen, OpenConversationsScreen) and bool(app.screen.query("#switch")))
    assert isinstance(app.screen, OpenConversationsScreen)
    return app.screen


def test_the_list_is_the_ones_opened_then_the_others_working_never_the_inbox():
    conversations = [
        _conversation("inbox", "Inbox", inbox=True),
        _conversation("a", "Trip"),
        _conversation("b", "Taxes"),
        _conversation("c", "Garden"),
    ]
    items = open_list(["b", "new", "inbox"], "b", "inbox", conversations, {"c", "inbox", "new"}, {"new"})
    assert items == [
        OpenItem("b", "Taxes", opened=True, current=True, running=False, waiting=False),
        OpenItem("new", "new conversation", opened=True, current=False, running=True, waiting=True),
        OpenItem("c", "Garden", opened=False, current=False, running=True, waiting=False),
    ]
    assert line(items[0]) == "  Taxes  [dim](shown)[/dim]"
    assert line(items[1]) == "? new conversation  [dim](waiting for you)[/dim]"
    assert line(items[2]) == "● Garden  [dim](working, not opened here)[/dim]"
    assert line(OpenItem("x", "[draft]", True, False, False, False)) == "  \\[draft]"


async def test_the_conversations_shown_here_are_listed_to_switch_and_close(app, client):
    client.conversations.items.append(_conversation("owner:taxes", "Taxes"))
    client.conversations.items.append(_conversation("owner:garden", "Garden"))
    client.tasks.tasks = [RunningTask("t1", "Claude Code", "owner:garden", "plant", _WHEN, [])]
    async with app.run_test(size=(120, 40)) as pilot:
        for thread_id in ("owner:taxes", "owner:garden"):
            await app._resume(thread_id)
        client.conversations.waiting["owner:taxes"] = [ApprovalRequired("i9", {"tool": "bash", "command": "ls"})]
        await pilot.press("ctrl+o")
        screen = await _opened(pilot, app)
        listed = screen.query_one("#open-conversations-list", OptionList)
        await wait_for(pilot, lambda: listed.option_count == 2)
        assert [listed.get_option_at_index(i).id for i in range(2)] == ["owner:taxes", "owner:garden"]
        assert "waiting for you" in str(listed.get_option_at_index(0).prompt)
        assert "working, shown" in str(listed.get_option_at_index(1).prompt)
        # The one shown can't be closed; another can, and only leaves the list.
        assert listed.highlighted == 1
        screen.query_one("#close-conversation", Button).press()
        await pilot.pause()
        assert listed.option_count == 2
        listed.highlighted = 0
        await pilot.press("enter")
        await wait_for(pilot, lambda: app._live.session.thread_id == "owner:taxes")
        await app._command_open("")
        screen = await _opened(pilot, app)
        listed = screen.query_one("#open-conversations-list", OptionList)
        await wait_for(pilot, lambda: listed.option_count == 2)
        listed.highlighted = 1
        screen.query_one("#close-conversation", Button).press()
        # Garden isn't open here any more, but its task still works: it stays, as one working elsewhere.
        await wait_for(pilot, lambda: "not opened here" in str(listed.get_option_at_index(1).prompt))
        assert app._opened == ["owner:taxes"]
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, OpenConversationsScreen))


async def test_with_none_open_it_says_how_to_open_one(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await app._command_open("")
        screen = await _opened(pilot, app)
        await wait_for(pilot, lambda: screen.query_one("#open-conversations").has_class("empty"))
        assert not screen.query_one("#switch").display
        assert not isinstance(app.screen, ConversationsScreen)
