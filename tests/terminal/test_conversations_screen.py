"""The /conversations dialog: moving through the list with the keys or clicks, previewing, and resuming."""

from textual.widgets import Markdown, OptionList

from assistant.core.agent import Conversation, ShownCall, ShownMessage, ShownStep
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


async def test_a_delegate_call_shows_the_subagents_steps_inside_it_when_resumed(app, client):
    from assistant_terminal.tui.widgets import ToolCall

    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b")]
    step = ShownStep("bash", {"command": "grep -r token logs"}, "token=42")
    client.conversations.said["owner:b"] = [
        ShownMessage("tool", "delegate", detail="Find the token", output="It's 42.", steps=[step]),
    ]
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: len(app.query(ToolCall)) == 2)
        call, inside = app.query(ToolCall)
        assert call.title == "✓ delegate(Find the token) · 1 step"
        assert inside.title == "✓ bash(grep -r token logs)" and inside in call.query(ToolCall)


async def test_a_tool_call_shows_its_start_and_loads_in_full_when_expanded(app, client):
    from textual.widgets import Static

    from assistant_terminal.tui.widgets import PartialToolCall

    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b")]
    client.conversations.said["owner:b"] = [
        ShownMessage("tool", "bash", detail="seq 1 100", output="1\n2…", call_id="c1", partial=True),
        ShownMessage("tool", "bash", detail="ls", output="a.txt…", call_id="gone", partial=True),
    ]
    client.conversations.calls[("owner:b", "c1")] = ShownCall("bash", {"command": "seq 1 100", "timeout": 5}, "1\n2\n3")
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: len(app.query(PartialToolCall)) == 2)
        loaded, failed = app.query(PartialToolCall)
        assert loaded.title == "✓ bash(seq 1 100)"
        assert str(loaded.query_one(".tool-result", Static).content) == "1\n2…"
        loaded.collapsed = failed.collapsed = False
        await wait_for(pilot, lambda: str(loaded.query_one(".tool-result", Static).content) == "1\n2\n3")
        assert loaded.title == '✓ bash({"command": "seq 1 100", "timeout": 5})'
        note = "a.txt…\n\nCouldn't load the whole call."
        await wait_for(pilot, lambda: str(failed.query_one(".tool-result", Static).content) == note)


async def test_a_step_inside_a_delegate_call_shows_its_start_and_loads_in_full_when_expanded(app, client):
    from textual.widgets import Static

    from assistant_terminal.tui.widgets import PartialToolCall, ToolCall

    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b")]
    steps = [
        ShownStep("bash", {"command": "cat log"}, "line…", partial=True),
        ShownStep("bash", {"command": "ls"}, "a"),
    ]
    client.conversations.said["owner:b"] = [
        ShownMessage("tool", "delegate", detail="Read the log", output="Done.", steps=steps, call_id="d1"),
    ]
    client.conversations.calls[("owner:b", "d1#0")] = ShownCall("bash", {"command": "cat log"}, "line\nline\n")
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: len(app.query(ToolCall)) == 3)
        [step] = app.query(PartialToolCall)
        assert step.title == "✓ bash(cat log)" and step in app.query(ToolCall).first().query(ToolCall)
        step.collapsed = False
        await wait_for(pilot, lambda: str(step.query_one(".tool-result", Static).content) == "line\nline")
