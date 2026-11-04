from textual.widgets import Button, Markdown

from lo9i.protocol import ConnectedClient
from lo9i_terminal.tui.screens import SessionsSection
from tests.terminal.conftest import section_shown, wait_for, wait_for_section


async def test_sessions_screen_lists_clients_and_follows_changes(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/sessions", "enter")
        screen = await wait_for_section(pilot, app, SessionsSection)

        def body() -> str:
            return screen.query_one("#sessions-body", Markdown).source

        await wait_for(pilot, lambda: "| cli (this one) | unix socket | 2026-09-30 09:00:00 UTC |" in body())
        client.clients.connected.append(ConnectedClient("web", "web", "127.0.0.1:50123", "2026-09-30T09:05:00+00:00"))
        await client.bus.put(("clients", {}))
        await wait_for(pilot, lambda: "| web | 127.0.0.1:50123 |" in body())
        screen.query_one("#close", Button).press()
        await wait_for(pilot, lambda: section_shown(app, SessionsSection) is None)
