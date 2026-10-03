"""/files: the files the user sent, with their type, size and conversation."""

from textual.widgets import Markdown

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

        await wait_for(pilot, lambda: "notes.txt" in body() and "2.0 KB" in body() and "Groceries" in body())
        client.files.items = []
        await screen.reload()
        await wait_for(pilot, lambda: "No files yet" in body())
