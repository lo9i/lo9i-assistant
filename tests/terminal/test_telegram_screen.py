from textual.widgets import Input, Markdown

from assistant.core.agent import TelegramStatus
from assistant_terminal.tui.screens import TelegramScreen
from tests.terminal.conftest import wait_for


async def test_connect_show_code_then_paired(app, client):
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/telegram", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, TelegramScreen))

        def body() -> str:
            return app.screen.query_one("#telegram-body", Markdown).source

        token = app.screen.query_one("#telegram-token", Input)
        token.value = "bad"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "Unauthorized" in body())
        token.value = "111:GOOD"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "lo9i-4821" in body())
        client.telegram.state = TelegramStatus(True, True, "lo9i_bot", ["Ani"], "", "")
        await client.bus.put(("integrations", {}))  # the bot paired someone
        await wait_for(pilot, lambda: "Paired: Ani" in body())
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, TelegramScreen))
