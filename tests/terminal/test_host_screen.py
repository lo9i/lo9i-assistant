from textual.widgets import Button, Markdown

from assistant_terminal.tui.screens import ConfirmScreen, HostScreen
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


async def _host_screen(pilot, app) -> HostScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/host", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, HostScreen))
    return app.screen


def _notices(app) -> str:
    return " ".join(str(n.message) for n in app._notifications)


async def test_restart_and_stop_ask_first(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _host_screen(pilot, app)
        screen.query_one("#restart", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert client.system.endings == []
        screen.query_one("#restart", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "restarts now" in _notices(app))
        screen.query_one("#stop", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "stops once the run in progress ends" in _notices(app))
        assert client.system.endings == ["restart", "stop"]


async def test_a_refused_stop_says_why(app, client):
    client.system.stop_refusal = "macOS would start the assistant again at once."
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _host_screen(pilot, app)
        screen.query_one("#stop", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "macOS would start the assistant again" in _notices(app))
        assert client.system.endings == []
