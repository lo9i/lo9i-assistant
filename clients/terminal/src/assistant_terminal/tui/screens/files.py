"""The files the user sent in their conversations, newest first, to save to Downloads or open in their
app on this computer. Refreshes when a conversation changes."""

import asyncio
import webbrowser
from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import FilesApi
from assistant.client.files import save_download
from assistant.core.agent import FileUnavailableError, UploadedFile
from assistant_terminal.files_text import describe
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_EMPTY = "No files yet. Files you attach to a message show up here."


class FilesScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, files: FilesApi) -> None:
        super().__init__()
        self._files = files
        self._shown: dict[str, UploadedFile] = {}
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="files"):
            yield Static("Files", id="files-title")
            with Horizontal(id="files-main"):
                yield OptionList(id="files-list")
                yield Static(classes="divider")
                with VerticalScroll(id="files-detail"):
                    yield Markdown(id="file-body")
            with Horizontal(id="files-buttons"):
                yield Button("Open", id="open")
                yield Button("Save to Downloads", variant="success", id="save")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a conversation changes: a message brought a file, or one was deleted with its files."""
        files = await self._files.list()
        self._shown = {f.path: f for f in files}
        options = self.query_one("#files-list", OptionList)
        options.clear_options()
        options.add_options([Option(f.name, id=f.path) for f in files])
        if self._selected not in self._shown:
            self._selected = files[0].path if files else None
        if self._selected is None:
            await self._body(_EMPTY)
            return
        options.highlighted = list(self._shown).index(self._selected)
        await self._body(describe(self._shown[self._selected]))

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id in self._shown:
            self._selected = event.option.id
            await self._body(describe(self._shown[event.option.id]))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        saved = await self._download()
        if saved is not None:
            self.notify(f"Saved to {saved}.")

    @on(Button.Pressed, "#open")
    @reports_daemon_unavailable
    async def _open(self) -> None:
        """Saved to Downloads first, then opened with the app this computer uses for it."""
        saved = await self._download()
        if saved is not None and not webbrowser.open(saved.as_uri()):
            self.notify(f"Saved to {saved}, but nothing here opens it.", severity="warning")

    async def _download(self) -> Path | None:
        file = self._shown.get(self._selected or "")
        if file is None:
            return None
        try:
            data = await self._files.content(file)
        except FileUnavailableError as e:
            self.notify(str(e), severity="error")
            return None
        return await asyncio.to_thread(save_download, file.name, data)

    async def _body(self, markdown: str) -> None:
        await self.query_one("#file-body", Markdown).update(markdown)
