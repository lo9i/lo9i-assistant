"""The app keeps running when the daemon can't be reached: the error shows as a notification."""

from textual.widgets import Button

from assistant.client import DaemonUnavailableError
from assistant.core.agent import ChannelStatus, SetupItem
from assistant_terminal.tui.screens import ChannelsScreen
from tests.terminal.conftest import wait_for

_DOWN = "Can't reach the daemon."


async def _unavailable(*args, **kwargs):
    raise DaemonUnavailableError(_DOWN)


def _reported(app) -> bool:
    return any(_DOWN in n.message for n in app._notifications)


async def test_a_screen_button_reports_it(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        client.channels.items["telegram"] = ChannelStatus(
            "telegram", True, True, [SetupItem("action", "New pairing code", "new_pairing_code")]
        )
        await pilot.press(*"/channels", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ChannelsScreen) and app.screen.query(".channel-action"))
        client.channels.press = _unavailable
        app.screen.query_one(".channel-action", Button).press()
        await wait_for(pilot, lambda: _reported(app))
        assert isinstance(app.screen, ChannelsScreen)


async def test_a_background_event_reports_it(app, client):
    async with app.run_test() as pilot:
        client.memory.snapshot = _unavailable
        await client.bus.put(("memory", {}))
        await wait_for(pilot, lambda: _reported(app))
        assert app.is_running


async def test_a_command_reports_it(app, client):
    client.new_thread = _unavailable
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/new", "enter")
        await wait_for(pilot, lambda: _reported(app))
        assert app.is_running
