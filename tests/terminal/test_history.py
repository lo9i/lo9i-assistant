"""Input history: Up and Down walk what was typed, across sessions."""

from textual.widgets import Input

from assistant_terminal.history import History
from assistant_terminal.tui.command_menu import CommandMenu
from assistant_terminal.tui.widgets import SystemNote
from tests.terminal.conftest import wait_for


def test_walks_back_and_forth_keeping_the_draft(tmp_path):
    history = History(tmp_path / "h", limit=3)
    for entry in ["a", "b", "b", "", "c", "d"]:
        history.add(entry)
    assert history.previous("typing") == "d"
    assert history.previous("d") == "c"
    assert history.previous("c") == "b"
    assert history.previous("b") is None  # "a" fell off the limit
    assert [history.next(), history.next(), history.next(), history.next()] == ["c", "d", "typing", None]


def test_survives_a_restart(tmp_path):
    History(tmp_path / "h", limit=10).add("hello")
    assert History(tmp_path / "h", limit=10).previous("") == "hello"


async def test_up_recalls_commands_without_opening_the_menu(app):
    async with app.run_test() as pilot:
        prompt, menu = app.query_one("#prompt", Input), app.query_one(CommandMenu)
        await pilot.click("#prompt")
        await pilot.press(*"/help", "enter")
        await pilot.press(*"/attach nope", "enter")
        await pilot.press("up")
        await wait_for(pilot, lambda: prompt.value == "/attach nope")
        await pilot.press("up")
        await wait_for(pilot, lambda: prompt.value == "/help")
        assert not menu.open
        await pilot.press("down", "down")
        await wait_for(pilot, lambda: prompt.value == "")
        await pilot.press("up", "up", "enter")
        await wait_for(pilot, lambda: len(app.query(SystemNote)) == 2)
