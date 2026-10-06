from dataclasses import replace

from textual.widgets import Button, Input, Markdown, OptionList

from assistant.core.agent import FoundServer, PluginUpdate, ServerField
from assistant.core.repositories.known import EXTRAS
from assistant_terminal.plugins_text import Plugin, by_category, describe
from assistant_terminal.tui.screens import PluginsScreen
from assistant_terminal.tui.screens.confirm import ConfirmWithOptionScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen, _field_input
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
        # The three are in Other, under its name.
        await wait_for(pilot, lambda: plugins.option_count == 4)
        assert "Kind: MCP server" in _body(screen) and screen.query_one("#install").display
        screen.query_one("#plugins-search", Input).value = "page"
        await wait_for(pilot, lambda: plugins.option_count == 2 and "## weather" in _body(screen))
        assert "Version: 1.1.0" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: "weather" in client.mcp.items)
        assert client.repositories.installed[-1][2][0].name == "weather"
        await wait_for(pilot, lambda: "State: installed" in _body(screen) and screen.query_one("#update").display)
        assert "Version: 1.0.0 → 1.1.0" in _body(screen)
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.mcp, "updated", None) == "weather")
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmWithOptionScreen))
        app.screen.query_one("#confirm-yes", Button).press()
        await wait_for(pilot, lambda: "weather" not in client.mcp.items)
        assert client.mcp.data_deleted is False  # the box starts unchecked


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


async def test_daily_update_checks_are_turned_on_and_off_here(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        checks = screen.query_one("#checks", Button)
        await wait_for(pilot, lambda: str(checks.label) == "Daily update checks: on")
        checks.press()
        await wait_for(
            pilot, lambda: not client.repositories.checks and str(checks.label) == "Daily update checks: off"
        )


async def test_new_plugin_updates_are_told_once_and_point_to_plugins(app, client):
    client.repositories.pending = [PluginUpdate("server", "weather", "1.0.0", "1.1.0")]
    async with app.run_test(size=(120, 44)) as pilot:
        await wait_for(pilot, lambda: _told(app) == 1)
        assert "Plugin update: weather 1.0.0 → 1.1.0. See /plugins." in _messages(app)
        client.bus.put_nowait(("plugins", {}))
        client.repositories.pending.append(PluginUpdate("skill", "expenses", "1.0.0", "2.0.0"))
        client.bus.put_nowait(("plugins", {}))
        await wait_for(pilot, lambda: _told(app) == 2)
        assert "Plugin update: expenses 1.0.0 → 2.0.0. See /plugins." in _messages(app)


def _messages(app) -> list[str]:
    return [str(n.message) for n in app._notifications]


def _told(app) -> int:
    return sum("Plugin update" in m for m in _messages(app))


def test_a_channel_plugin_is_labelled_as_a_channel():
    telegram = FoundServer("telegram", "Chat on Telegram", "none", [], True, channel=True)
    slack = FoundServer("slack", "Slack", "stdio", [], True, skill=True, channel=True)
    assert Plugin("telegram", False, server=telegram).kind == "Channel"
    assert Plugin("slack", False, server=slack).kind == "MCP server · channel · skill"
    assert "Runs: on the assistant's computer" in describe(Plugin("telegram", False, server=telegram))


def test_plugins_are_grouped_by_their_categorys_group_with_other_last():
    def plugin(name: str, category: str) -> Plugin:
        return Plugin(name, False, server=FoundServer(name, "", "stdio", [], False, category=category))

    shown = [
        plugin("misc", "other/general"),
        plugin("ledger", "apps/finance"),
        plugin("bot", "communications/chat"),
        plugin("mail", "communications/email"),
    ]
    assert [(c, [p.name for p in g]) for c, g in by_category(shown)] == [
        ("apps", ["ledger"]),
        ("communications", ["bot", "mail"]),
        ("other", ["misc"]),
    ]
    assert "Category: Apps / Finance" in describe(shown[1])


def test_a_value_the_daemon_already_has_may_be_left_empty():
    token = ServerField("BOT_TOKEN", "Bot token", secret=True)
    telegram = FoundServer("telegram", "Chat on Telegram", "none", [token], True, known_fields=["BOT_TOKEN"])
    assert "leave empty to keep the one you set before" in str(_field_input(telegram, token).placeholder)
    asked = replace(telegram, known_fields=[])
    assert "leave empty" not in str(_field_input(asked, token).placeholder)


def test_an_optional_field_and_the_shared_copilot_login_are_explained():
    from assistant.core.agent import RepositoryContents
    from assistant_terminal.tui.screens.repository_install import _guide

    token = ServerField("CLAUDE_TOKEN", "Claude token", secret=True, optional=True)
    coder = FoundServer(
        "claude-code", "Coding tasks", "stdio", [token], False, steps=["Paste it."], model_login="copilot"
    )
    assert "optional" in str(_field_input(coder, token).placeholder)
    guide = _guide(RepositoryContents(skills=[], servers=[coder]))
    assert guide.startswith("It uses your GitHub Copilot login from /model") and "1. Paste it." in guide
