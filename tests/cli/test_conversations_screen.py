"""The /conversations dialog: moving through the list with the keys or clicks, previewing, and resuming."""

from textual.widgets import Markdown, OptionList

from assistant.core.agent import Conversation, ShownMessage
from assistant.gateways.cli.tui.screens import ConversationsScreen
from tests.cli.conftest import wait_for

_AT = "2030-01-01T09:00:00+00:00"


async def test_arrows_and_clicks_show_a_conversation_and_enter_resumes(app, client):
    client.conversations.items = [Conversation(f"owner:{n}", f"trip {n}", _AT, _AT) for n in ("abc", "b", "c")]
    client.conversations.said["owner:b"] = [ShownMessage("user", "book the hotel")]
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        options = app.screen.query_one(OptionList)
        assert str(options.get_option_at_index(0).prompt) == "Tue 01 Jan 09:00"
        await pilot.press("down")
        body = app.screen.query_one("#conversation-body", Markdown)
        await wait_for(pilot, lambda: options.highlighted == 1 and "book the hotel" in body.source)
        await pilot.click(options, offset=(2, 2))  # the third: shown, not resumed
        await wait_for(pilot, lambda: options.highlighted == 2)
        assert isinstance(app.screen, ConversationsScreen)
        await pilot.press("up", "enter")
        await wait_for(pilot, lambda: app.sub_title == "owner:b")
        assert client.active_thread == "owner:b"
