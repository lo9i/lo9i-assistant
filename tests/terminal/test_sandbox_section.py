from textual.widgets import Button, Markdown

from lo9i_terminal.tui.screens import SandboxSection
from tests.terminal.conftest import wait_for, wait_for_section


async def test_it_says_why_it_cant_be_turned_on_then_turns_on(app, client):
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/sandbox", "enter")
        await wait_for_section(pilot, app, SandboxSection)

        def body() -> str:
            return app.screen.query_one("#sandbox-body", Markdown).source

        turn_on = app.screen.query_one("#sandbox-on", Button)
        await wait_for(pilot, lambda: "isn't running" in body())
        assert turn_on.disabled
        client.sandbox.available = True
        await app.screen.query_one(SandboxSection).reload()
        await wait_for(pilot, lambda: not turn_on.disabled)
        turn_on.press()
        await wait_for(pilot, lambda: client.sandbox.enabled and "image python:3.12-slim" in body())
        assert not turn_on.display and app.screen.query_one("#sandbox-off").display
