from textual.widgets import Markdown

from assistant.gateways.cli.tui.screens import SessionsScreen
from assistant.protocol import ConnectedClient
from tests.cli.conftest import wait_for


async def test_sessions_screen_lists_clients_and_follows_changes(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/sessions", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, SessionsScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#sessions-body", Markdown).source

        await wait_for(pilot, lambda: "| cli (this one) | unix socket | 2026-09-30 09:00:00 UTC |" in body())
        client.clients.connected.append(ConnectedClient("web", "web", "127.0.0.1:50123", "2026-09-30T09:05:00+00:00"))
        await client.bus.put(("clients", {}))
        await wait_for(pilot, lambda: "| web | 127.0.0.1:50123 |" in body())
        await pilot.press("enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, SessionsScreen))
