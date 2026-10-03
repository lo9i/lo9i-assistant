from textual.widgets import Button, Input, Markdown, OptionList

from assistant.core.repositories.known import EXTRAS
from assistant_terminal.tui.screens import ConfirmScreen, PluginsScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen
from tests.terminal.conftest import wait_for


async def _open(pilot, app) -> PluginsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/plugins", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, PluginsScreen))
    return app.screen


def _body(screen) -> str:
    return screen.query_one("#plugin-body", Markdown).source


async def test_lists_the_extras_with_a_search_and_installs_one_that_asks_for_nothing_at_once(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        plugins = screen.query_one("#plugins-list", OptionList)
        await wait_for(pilot, lambda: plugins.option_count == 3)
        assert "Kind: MCP server" in _body(screen) and screen.query_one("#install").display
        screen.query_one("#plugins-search", Input).value = "page"
        await wait_for(pilot, lambda: plugins.option_count == 1 and "## weather" in _body(screen))
        assert "Version: 1.1.0" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: "weather" in client.mcp.items)
        assert client.repositories.installed[-1][2][0].name == "weather"
        await wait_for(pilot, lambda: "State: installed" in _body(screen) and screen.query_one("#update").display)
        assert "Version: 1.0.0 → 1.1.0" in _body(screen)
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.mcp, "updated", None) == "weather")
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "weather" not in client.mcp.items)


async def test_a_plugin_that_asks_for_values_gets_a_screen_for_just_those(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "## calendar" in _body(screen))
        assert "Asks for: User, Password" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        install = app.screen
        fields = list(install.query("#repository-fields Input").results(Input))
        await wait_for(pilot, lambda: len(list(install.query("#repository-fields Input"))) == 2)
        fields = list(install.query("#repository-fields Input").results(Input))
        fields[0].value, fields[1].value = "ana", "pw"
        install.query_one("#install", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "calendar" in client.mcp.items)
        assert client.repositories.installed[-1][0] == EXTRAS
