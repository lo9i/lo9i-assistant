from textual.widgets import RichLog, Select, Static, Switch

from assistant_terminal.tui.screens import LogsScreen
from tests.terminal.conftest import _log, wait_for


def _text(screen: LogsScreen) -> str:
    return "\n".join(line.text for line in screen.query_one("#logs-body", RichLog).lines)


async def _open(pilot, app) -> LogsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/logs", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, LogsScreen))
    return app.screen


async def test_it_shows_the_daemon_log_and_filters_it(app):
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "crashed" in _text(screen))
        assert "connected" in _text(screen) and "slow" in _text(screen)
        assert "daemon.log" in str(screen.query_one("#logs-title", Static).render())
        screen.query_one("#logs-level", Select).value = "WARNING"
        await wait_for(pilot, lambda: "connected" not in _text(screen))
        assert "slow" in _text(screen)
        screen.query_one("#logs-component", Select).value = "agent"
        await wait_for(pilot, lambda: "slow" not in _text(screen))
        assert "crashed" in _text(screen)


async def test_following_adds_new_entries_until_turned_off(app, client):
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "crashed" in _text(screen))
        screen.query_one("#logs-follow", Switch).value = True
        await wait_for(pilot, lambda: client.logs.following == 1)
        client.logs.live.put_nowait(_log("ERROR", "fresh"))
        await wait_for(pilot, lambda: "fresh" in _text(screen))
        screen.query_one("#logs-follow", Switch).value = False
        await wait_for(pilot, lambda: client.logs.following == 0)
