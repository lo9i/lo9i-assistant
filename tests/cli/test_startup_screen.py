from textual.widgets import Button, Markdown

from assistant.gateways.cli.tui.screens import StartupScreen
from tests.cli.conftest import wait_for


async def test_enable_cancel_and_disable(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/startup", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, StartupScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#startup-body", Markdown).source

        await wait_for(pilot, lambda: "Start at boot: **off**" in body())
        client.system.cancel_password = True
        screen.query_one("#enable", Button).press()
        await wait_for(pilot, lambda: "Cancelled." in body())
        client.system.cancel_password = False
        screen.query_one("#enable", Button).press()
        await wait_for(pilot, lambda: "**on** (with Ollama)" in body() and "restarts under macOS" in body())
        assert not screen.query_one("#enable").display and screen.query_one("#disable").display
        screen.query_one("#disable", Button).press()
        await wait_for(pilot, lambda: "Start at boot: **off**" in body())
