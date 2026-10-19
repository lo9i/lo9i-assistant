"""The /conversations dialog: moving through the list with the keys or clicks, previewing, and resuming."""

from textual.widgets import Markdown, OptionList

from assistant.core.agent import Conversation, ShownMessage
from assistant_terminal.tui.screens import ConversationsScreen
from tests.terminal.conftest import wait_for

_AT = "2030-01-01T09:00:00+00:00"


async def test_arrows_and_clicks_show_a_conversation_and_enter_resumes(app, client):
    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b", "c")]
    client.conversations.said["owner:b"] = [ShownMessage("user", "book the hotel")]
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        options = app.screen.query_one(OptionList)
        assert str(options.get_option_at_index(0).prompt) == "trip abc\nTue 01 Jan 09:00"
        await pilot.press("down")
        body = app.screen.query_one("#conversation-body", Markdown)
        await wait_for(pilot, lambda: options.highlighted == 1 and "book the hotel" in body.source)
        await pilot.click(options, offset=(2, 4))  # the third (two lines each): shown, not resumed
        await wait_for(pilot, lambda: options.highlighted == 2)
        assert isinstance(app.screen, ConversationsScreen)
        await pilot.press("up", "enter")
        await wait_for(pilot, lambda: app.sub_title == "owner:b")
        assert client.active_thread == "owner:b"


async def test_delete_asks_first_and_isnt_offered_for_the_current_one(app, client):
    from textual.widgets import Button

    from assistant_terminal.tui.screens import ConfirmScreen

    async with app.run_test() as pilot:
        current = app._live.session.thread_id
        client.conversations.items = [Conversation(t, t, _AT, _AT) for t in (current, "owner:old")]
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        screen = app.screen
        delete = screen.query_one("#delete", Button)
        await wait_for(pilot, lambda: screen.query_one(OptionList).highlighted == 0 and delete.disabled)
        await pilot.press("down")
        await wait_for(pilot, lambda: not delete.disabled)
        delete.press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: [c.thread_id for c in client.conversations.items] == [current])


async def test_a_handed_off_agents_thinking_and_tool_calls_show_again_when_resumed(app, client):
    from assistant_terminal.tui.widgets import AssistantMessage, CarriedNote, ThinkingNote, ToolCall

    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b")]
    client.conversations.said["owner:b"] = [
        ShownMessage("carried", "**You:** which tests fail?"),
        ShownMessage("user", "fix the tests"),
        ShownMessage("thinking", "The test expects a list."),
        ShownMessage("tool", "Bash", detail="pytest -q", output="1 failed"),
        ShownMessage("assistant", "Fixed it."),
    ]
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: app.sub_title == "owner:b" and app.query(ToolCall))
        chat = app.query_one("#chat")
        assert [type(w) for w in chat.children][-3:] == [ThinkingNote, ToolCall, AssistantMessage]
        assert isinstance(chat.children[0], CarriedNote)  # the quick exchange from the inbox, before it
        assert app.query_one(ToolCall).title == "✓ Bash(pytest -q)"
