"""A plugin's sign-in with the user's own OAuth app, from /plugins or its setup in a conversation: signing in, the
browser's address pasted back, and signing out."""

from dataclasses import replace

from textual.widgets import Button, Input, Markdown

from assistant.core.agent import FoundServer
from assistant_terminal.tui.screens import PluginSignInScreen, PluginsScreen
from tests.terminal.conftest import _mcp_status, wait_for


async def test_signs_in_with_the_users_oauth_app_and_out(app, client, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    client.mcp.items["drive"] = replace(_mcp_status("drive"), oauth="google")
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await app.push_screen(PluginSignInScreen(client.mcp, client.oauth, "drive", "google"))
        await wait_for(pilot, lambda: isinstance(app.screen, PluginSignInScreen))
        screen = app.screen
        body = screen.query_one("#plugin-sign-in-body", Markdown)
        await wait_for(
            pilot, lambda: "Not signed in yet: drive's tools work once you sign in to Google." in body.source
        )
        assert "http://localhost:8765/app/oauth" in body.source and not screen.query_one("#sign-out").display
        # No client ID: the daemon says what's missing.
        screen.query_one("#sign-in", Button).press()
        await wait_for(pilot, lambda: "Enter your OAuth app's client ID." in body.source)
        screen.query_one("#plugin-client-id", Input).value = "client-1"
        screen.query_one("#plugin-client-secret", Input).value = "secret-1"
        screen.query_one("#sign-in", Button).press()
        await wait_for(pilot, lambda: bool(opened) and screen.query_one("#finish").display)
        assert client.mcp.plugin_signing_in == ("drive", "http://localhost:8765/app/oauth", "client-1", "secret-1")
        screen.query_one("#plugin-returned", Input).value = "http://localhost:8765/app/oauth?code=c1&state=p1"
        screen.query_one("#finish", Button).press()
        await wait_for(pilot, lambda: "Signed in to Google as me@gmail.com." in body.source)
        assert screen.query_one("#sign-out").display and not screen.query_one("#finish").display
        screen.query_one("#sign-out", Button).press()
        await wait_for(pilot, lambda: "Not signed in yet" in body.source)
        assert client.mcp.items["drive"].signed_in_as == ""


async def test_plugins_open_the_sign_in_of_an_installed_plugin_that_signs_in(app, client):
    drive = FoundServer(
        "drive", "Google Drive", "stdio", [], False, installed=True, category="productivity/documents", oauth="google"
    )
    client.repositories.more = [drive]
    client.mcp.items["drive"] = replace(_mcp_status("drive"), oauth="google")
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/plugins", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, PluginsScreen))
        plugins = app.screen
        await wait_for(pilot, lambda: plugins.query_one("#plugin-sign-in").display)
        assert not plugins.query_one("#email-accounts").display
        plugins.query_one("#plugin-sign-in", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, PluginSignInScreen))


async def test_a_sign_in_its_check_refused_in_the_browser_shows_in_its_screen(app, client):
    client.mcp.items["drive"] = replace(_mcp_status("drive"), oauth="google")
    refusal = "The sign-in wasn't kept. drive: Google refused the account."
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await app.push_screen(PluginSignInScreen(client.mcp, client.oauth, "drive", "google"))
        await wait_for(pilot, lambda: isinstance(app.screen, PluginSignInScreen))
        body = app.screen.query_one("#plugin-sign-in-body", Markdown)
        await wait_for(pilot, lambda: "Not signed in yet" in body.source)
        # Another plugin's refusal isn't this screen's.
        await app.show_sign_in_refused({"name": "contacts", "error": "contacts: no"})
        assert "contacts: no" not in body.source
        await app.show_sign_in_refused({"name": "drive", "error": refusal})
        await wait_for(pilot, lambda: refusal in body.source)
