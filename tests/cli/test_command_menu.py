from textual.widgets import Input

from assistant.gateways.cli.commands import COMMANDS, help_lines
from assistant.gateways.cli.tui.command_menu import CommandMenu
from assistant.gateways.cli.tui.widgets import SystemNote


async def test_menu_filters_moves_and_completes(app):
    async with app.run_test() as pilot:
        menu, prompt = app.query_one(CommandMenu), app.query_one("#prompt", Input)
        await pilot.click("#prompt")
        await pilot.press("/")
        assert menu.open and menu.highlighted.name == "/new"
        await pilot.press("up")
        assert menu.highlighted.name == COMMANDS[-1].name  # wraps
        await pilot.press("down", "down", "tab")
        assert prompt.value == "/conversations"
        prompt.value = ""
        await pilot.press("/", "t")
        assert [c.name for c in menu._matches] == ["/telegram"]
        prompt.value = "hello"
        await pilot.pause()
        assert not menu.open


async def test_enter_runs_the_highlighted_command(app):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press("/", "h", "enter")  # /help
        await pilot.pause(0.2)
        assert len(app.query(SystemNote)) == 1


def test_help_lists_every_command():
    assert len(help_lines()) == len(COMMANDS)
