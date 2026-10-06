"""/files: the files in the conversations, with their type, size, where they came from and conversation."""

from textual.widgets import Markdown, OptionList

from assistant_terminal.tui.screens import FilesScreen
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
