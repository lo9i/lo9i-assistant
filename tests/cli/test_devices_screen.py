"""/devices: pair a browser with a code, see devices, revoke one after confirming."""

from textual.widgets import Button, Markdown

from assistant.gateways.cli.tui.screens import ConfirmScreen, DevicesScreen
from tests.cli.conftest import wait_for


async def test_pair_a_browser_and_revoke_a_device(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/devices", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, DevicesScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#device-body", Markdown).source

        await wait_for(pilot, lambda: "203.0.113.7" in body())
        screen.query_one("#pair", Button).press()
        await wait_for(pilot, lambda: "K7QM-2XPD" in body())
        screen.query_one("#revoke", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.devices.items == [] and "No devices paired yet" in body())
        assert not screen.query_one("#revoke").display
