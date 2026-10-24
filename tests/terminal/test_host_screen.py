from textual.widgets import Button, Markdown

from assistant.protocol import Commit
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


async def test_checks_for_an_update_lists_whats_new_and_installs_it_after_asking(app, client):
    client.system.upstream_has = [Commit("b2c3d4e5", "Second", "2026-10-24T13:00:00Z")]
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _host_screen(pilot, app)

        def body() -> str:
            return screen.query_one("#host-body", Markdown).source

        await wait_for(pilot, lambda: "| lo9i | v0.1.0 · a1b2c3d · 2026-10-24 |" in body())
        assert "Not checked yet." in body() and screen.query_one("#update", Button).disabled
        screen.query_one("#check", Button).press()
        await wait_for(pilot, lambda: "1 new change on origin/main." in body())
        assert "- `b2c3d4e` Second" in body()
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "Downloading the update…" in body())
        assert client.system.updates_started == 1


async def test_every_restart_or_stop_announced_shows_in_the_app(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await client.bus.put(("ending", {"ending": "restart", "waiting_for_runs": 2}))
        await wait_for(pilot, lambda: "restarts once the 2 runs in progress end" in _notices(app))
        assert "reconnects when it's back" in _notices(app)


async def test_the_app_says_while_the_assistant_cant_be_reached_and_when_its_back(app, client):
    from assistant_terminal.tui.widgets import ConnectionNote
    from tests.terminal.conftest import LOST, OPEN

    async with app.run_test(size=(110, 40)) as pilot:
        note = app.query_one(ConnectionNote)
        assert not note.display
        await client.bus.put((LOST, {}))
        await wait_for(pilot, lambda: note.display)
        assert "Can't reach the assistant right now" in str(note.render())
        await client.bus.put((OPEN, {}))
        await wait_for(pilot, lambda: not note.display)
        assert "Connected to the assistant again." in _notices(app)
