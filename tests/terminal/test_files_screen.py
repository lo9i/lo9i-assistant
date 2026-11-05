"""/files: the files in the conversations, with their type, size, where they came from and conversation."""

from textual.widgets import Markdown, OptionList

from lo9i_terminal.tui.screens import ConfirmScreen, FilesScreen
from tests.terminal.conftest import wait_for


async def test_lists_the_files_sent(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/files", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, FilesScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#file-body", Markdown).source

        await wait_for(pilot, lambda: "notes.txt" in body() and "2.0 KB" in body() and "Sent" in body())
        screen.query_one("#files-list", OptionList).highlighted = 1
        await wait_for(
            pilot, lambda: "chart.png" in body() and "From sheets: chart" in body() and "Groceries" in body()
        )
        client.files.items = []
        await screen.reload()
        await wait_for(pilot, lambda: "No files yet" in body())


async def test_a_file_is_saved_to_downloads(app, client, tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/files", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, FilesScreen))
        app.screen.query_one("#save").press()
        await wait_for(pilot, lambda: (tmp_path / "Downloads" / "notes.txt").exists())
        assert (tmp_path / "Downloads" / "notes.txt").read_bytes() == b"buy milk"


async def test_a_file_is_deleted_once_confirmed(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/files", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, FilesScreen))
        screen = app.screen
        await wait_for(pilot, lambda: "notes.txt" in screen.query_one("#file-body", Markdown).source)
        screen.query_one("#delete").press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "chart.png" in screen.query_one("#file-body", Markdown).source)
        assert [f.name for f in client.files.items] == ["chart.png"]


async def test_a_double_click_opens_the_file_and_one_click_only_picks_it(app, client, tmp_path, monkeypatch):
    from pathlib import Path

    from lo9i_terminal.tui.screens import files

    opened: list[str] = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(files.webbrowser, "open", lambda uri: opened.append(uri) or True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/files", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, FilesScreen))
        screen = app.screen
        await wait_for(pilot, lambda: "notes.txt" in screen.query_one("#file-body", Markdown).source)
        await pilot.click("#files-list", offset=(2, 2))  # the second, under its card's top line
        await wait_for(pilot, lambda: "chart.png" in screen.query_one("#file-body", Markdown).source)
        assert opened == []
        await pilot.double_click("#files-list", offset=(2, 2))
        await wait_for(pilot, lambda: opened == [(tmp_path / "Downloads" / "chart.png").as_uri()])
