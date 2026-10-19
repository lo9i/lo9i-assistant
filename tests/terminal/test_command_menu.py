from textual.widgets import Input

from assistant_terminal.commands import COMMANDS, help_lines
from assistant_terminal.tui.command_menu import CommandMenu
from assistant_terminal.tui.widgets import SystemNote


async def test_menu_filters_moves_and_completes(app):
    async with app.run_test() as pilot:
        menu, prompt = app.query_one(CommandMenu), app.query_one("#prompt", Input)
        await pilot.click("#prompt")
        await pilot.press("/")
        assert menu.open and menu.highlighted.name == "/new"
        await pilot.press("up")
        assert menu.highlighted.name == "/claude"  # wraps to the last: the agents' commands follow the built-in ones
        await pilot.press("down", "down", "tab")
        assert prompt.value == "/conversations"
        prompt.value = ""
        await pilot.press("/", "p", "l")
        assert [c.name for c in menu._matches] == ["/plugins"]
        prompt.value = "hello"
        await pilot.pause()
        assert not menu.open


async def test_enter_runs_the_highlighted_command(app):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press("/", "h", "e", "enter")  # /help
        await pilot.pause(0.2)
        assert len(app.query(SystemNote)) == 2  # the conversations the app opened to, then the help


def test_help_lists_every_command():
    assert len(help_lines()) == len(COMMANDS)


async def test_the_highlighted_command_stays_in_view(app):
    """More commands match "/" than the menu shows, so it scrolls to the highlight."""
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press("/")
        menu = app.query_one(CommandMenu)
        for key in ("up", "down", "down"):  # wrap to the last command, then back to the top
            await pilot.press(key)
            await pilot.pause()
            row = next(r for r in menu.query(".command-row") if r.has_class("highlighted"))
            assert menu.region.contains_region(row.region), key
