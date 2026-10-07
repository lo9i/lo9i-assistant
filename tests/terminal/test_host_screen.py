from textual.widgets import Button, Markdown

from assistant_terminal.tui.screens import HostScreen
from tests.terminal.conftest import wait_for


async def test_shows_the_host_and_reads_it_again_on_refresh(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/host", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HostScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#host-body", Markdown).source

        await wait_for(pilot, lambda: "| Host | board |" in body())
        assert "| Memory | 2.0 GB / 4.0 GB (50.0%) |" in body()
        assert "| Uptime | 1d 1h 1m |" in body() and "| Load avg | 0.09 / 0.09 / 0.04 |" in body()
        screen.query_one("#refresh", Button).press()
        await wait_for(pilot, lambda: client.system.host_reads == 2)
