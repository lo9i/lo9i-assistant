from textual.widgets import Button, Input, Markdown, OptionList, SelectionList, TextArea

from assistant_terminal.mcp_text import parse_command, parse_pairs, selection
from assistant_terminal.tui.screens import ConfirmScreen, McpScreen
from assistant_terminal.tui.screens.mcp_add import McpAddScreen
from tests.terminal.conftest import wait_for


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


async def test_installs_a_server_from_a_repository_and_updates_it(app, client):
    from assistant.core.repositories.known import EXTRAS
    from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen

    async with app.run_test(size=(120, 50)) as pilot:
        screen = await _open(pilot, app)
        assert not screen.query_one("#update").display  # notes was added by hand
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        install = app.screen
        found = install.query_one("#repository-found", SelectionList)
        await wait_for(pilot, lambda: found.option_count == 2)
        found.select("server:calendar")
        for field, value in zip(install.query("#repository-fields Input").results(Input), ["ana", "pw"], strict=True):
            field.value = value
        install.query_one("#install", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "calendar" in client.mcp.items)
        screen.query_one("#mcp-list", OptionList).highlighted = 1
        await wait_for(pilot, lambda: f"Installed from {EXTRAS}" in screen.query_one("#mcp-body", Markdown).source)
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.mcp, "updated", None) == "calendar")
