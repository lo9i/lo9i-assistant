from dataclasses import replace

from textual.widgets import Button, Input, Markdown, OptionList, Select, SelectionList, TextArea

from assistant_terminal.mcp_text import describe, parse_command, parse_pairs, selection, summary
from assistant_terminal.tui.screens import ConfirmScreen, McpScreen
from assistant_terminal.tui.screens.mcp_add import McpAddScreen
from assistant_terminal.tui.screens.mcp_sign_in import McpSignInScreen
from tests.terminal.conftest import _mcp_status, wait_for


async def _open(pilot, app) -> McpScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/mcp", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, McpScreen))
    return app.screen


async def test_shows_a_server_chooses_tools_trusts_and_removes(app, client):
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await _open(pilot, app)

        def body() -> str:
            return screen.query_one("#mcp-body", Markdown).source

        await wait_for(pilot, lambda: "notes-server" in body())
        assert "TOKEN (values hidden)" in body() and "Not trusted" in body()
        tools = screen.query_one("#mcp-tools", SelectionList)
        tools.deselect("add_note")
        screen.query_one("#save-tools", Button).press()
        await wait_for(pilot, lambda: client.mcp.items["notes"].include == ["read_notes"])
        screen.query_one("#trust", Button).press()
        await wait_for(pilot, lambda: client.mcp.items["notes"].trusted and "Trusted" in body())
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: not client.mcp.items and screen.query_one("#mcp").has_class("empty"))


async def test_adds_a_local_server_after_looking_at_its_tools(app, client):
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#add", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, McpAddScreen))
        dialog = app.screen
        dialog.query_one("#mcp-name", Input).value = "github"
        dialog.query_one("#mcp-command", Input).value = "npx -y @modelcontextprotocol/server-github"
        dialog.query_one("#mcp-secrets", TextArea).text = "GITHUB_TOKEN=secret"
        dialog.query_one("#probe", Button).press()
        tools = dialog.query_one("#mcp-add-tools", SelectionList)
        await wait_for(pilot, lambda: tools.display and len(tools.selected) == 2)
        tools.deselect("delete")
        dialog.query_one("#add", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "github" in client.mcp.items)
        added = client.mcp.added[0]
        assert (added.command, added.args) == ("npx", ["-y", "@modelcontextprotocol/server-github"])
        assert added.env == {"GITHUB_TOKEN": "secret"} and added.include == ["search"] and not added.trusted


async def test_a_remote_server_that_asks_to_sign_in_is_added_then_signed_in(app, client, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "assistant_terminal.tui.screens.mcp_sign_in.webbrowser.open", lambda url: opened.append(url) or False
    )
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#add", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, McpAddScreen))
        dialog = app.screen
        dialog.query_one("#mcp-kind", Select).value = "remote"
        dialog.query_one("#mcp-name", Input).value = "linear"
        dialog.query_one("#mcp-url", Input).value = "https://mcp.linear.app/mcp"
        dialog.query_one("#probe", Button).press()
        message = dialog.query_one("#mcp-add-message", Markdown)
        await wait_for(pilot, lambda: "asks you to sign in" in message.source and dialog.query_one("#add").display)
        dialog.query_one("#add", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "linear" in client.mcp.items)
        client.mcp.items["linear"].status = "needs_sign_in"
        await screen.reload()
        screen.query_one("#mcp-list", OptionList).highlighted = list(client.mcp.items).index("linear")
        await wait_for(pilot, lambda: screen.query_one("#sign-in").display)
        screen.query_one("#sign-in", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, McpSignInScreen))
        sign_in = app.screen
        body = sign_in.query_one("#mcp-sign-in-body", Markdown)
        await wait_for(pilot, lambda: "sign in" in body.source and opened)
        assert client.mcp.signing_in == ("linear", "http://localhost:8765/app/oauth")
        sign_in.query_one("#mcp-returned", Input).value = "http://localhost:8765/app/oauth?code=c1&state=m1"
        sign_in.query_one("#finish", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and client.mcp.items["linear"].status == "connected")
        assert not screen.query_one("#sign-in").display


def test_parsing_what_the_user_types():
    assert parse_pairs("A=1\n\n B = two=2 ", "=") == {"A": "1", "B": "two=2"}
    assert parse_pairs("Authorization: Bearer x", ":") == {"Authorization": "Bearer x"}
    assert parse_command('uvx "my server" --flag') == ("uvx", ["my server", "--flag"])
    try:
        parse_pairs("no separator", "=")
    except ValueError as e:
        assert "KEY=value" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_the_checked_tools_become_include_and_exclude_lists():
    from assistant.core.agent import McpToolInfo

    tools = [McpToolInfo("a", "", True, True), McpToolInfo("b", "", False, True)]
    assert selection(tools, {"a", "b"}) == ([], [])  # tools added later are offered too
    assert selection(tools, {"b"}) == (["b"], [])
    assert selection(tools, set()) == ([], ["*"])


async def test_a_server_installed_from_the_extras_is_updated_here(app, client):
    from assistant.core.agent import ServerValues
    from assistant.core.repositories.known import EXTRAS

    async with app.run_test(size=(120, 50)) as pilot:
        screen = await _open(pilot, app)
        assert not screen.query("#install")  # the extras are installed from /plugins
        assert not screen.query_one("#update").display  # notes was added by hand
        await client.repositories.install([], [ServerValues("calendar", {"CAL_USER": "ana", "CAL_PASSWORD": "pw"})])
        await screen.reload()
        client.mcp.items["calendar"].plugin = "calendar"
        await screen.reload()
        screen.query_one("#mcp-list", OptionList).highlighted = 1
        await wait_for(pilot, lambda: f"Installed from {EXTRAS}" in screen.query_one("#mcp-body", Markdown).source)
        # What a plugin installed is removed with the plugin, in /plugins.
        assert not screen.query_one("#remove").display
        assert "remove the calendar plugin in /plugins" in screen.query_one("#mcp-body", Markdown).source
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.mcp, "updated", None) == "calendar")


def test_a_failing_server_is_marked_and_its_last_failure_shown():
    server = _mcp_status("notes")
    server.failures, server.failure, server.failed_at = 3, "add_note: disk full", "2026-10-03T12:00:00+00:00"
    server.failing = True
    assert summary(server) == "notes · connected · failing"
    assert "**Failed 3 times in a row.**" in describe(server) and "add_note: disk full" in describe(server)
    server.failures, server.failing = 0, False
    assert summary(server) == "notes · connected" and "Failed" not in describe(server)


async def test_a_lost_sign_in_shows_a_notification(app, client):
    async with app.run_test() as pilot:
        await client.bus.put(("signed_out", {"name": "linear", "error": "linear needs you to sign in again."}))
        await wait_for(
            pilot, lambda: any("linear needs you to sign in again" in str(n.message) for n in app._notifications)
        )


async def test_a_plugin_that_is_only_a_chat_channel_is_not_listed(app, client):
    """It has no tools; Slack has tools as well as its channel, so it is."""
    client.mcp.items["telegram"] = replace(_mcp_status("telegram"), transport="channel", tools=[])
    client.mcp.items["slack"] = replace(_mcp_status("slack"), channel=True)
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await _open(pilot, app)
        options = screen.query_one("#mcp-list", OptionList)
        await wait_for(pilot, lambda: options.option_count == 2)
        assert [options.get_option_at_index(i).id for i in range(2)] == ["notes", "slack"]
