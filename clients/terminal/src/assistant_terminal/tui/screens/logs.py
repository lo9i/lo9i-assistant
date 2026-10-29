"""The daemon's log: the latest entries of a log file or its process output, picked by level, component
and how many, or followed live while Follow is on (a stream from the daemon, not a timer). Record sets
the lowest level the daemon writes, at once."""

from contextlib import aclosing
from typing import Any, ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RichLog, Select, Static, Switch

from assistant.client.daemon_client import LogsApi
from assistant.core.logs import LogEntry, LogOptions, LogPage
from assistant_terminal.i18n import t, translatable
from assistant_terminal.logs_text import log_line
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

LINES = (50, 100, 200, 500)
_DEFAULT_LINES = 100
_ALL = ""
_DAEMON = "daemon"
_RECORDED = "INFO"
_STYLES = {"WARNING": "yellow", "ERROR": "red", "CRITICAL": "bold red"}
_LEVELS = {
    "DEBUG": translatable("Debug"),
    "INFO": translatable("Info"),
    "WARNING": translatable("Warning"),
    "ERROR": translatable("Error"),
    "CRITICAL": translatable("Critical"),
}


def _level(level: str) -> str:
    return t(_LEVELS[level]) if level in _LEVELS else level.title()


class LogsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", t("Close"))]

    def __init__(self, logs: LogsApi) -> None:
        super().__init__()
        self._logs = logs

    def compose(self) -> ComposeResult:
        with Vertical(id="logs"):
            with Horizontal(id="logs-filters"):
                # Until the daemon lists its files: the one it always has.
                yield Select[str](
                    [(f"{_DAEMON}.log", _DAEMON)], value=_DAEMON, allow_blank=False, id="logs-file", classes="filter"
                )
                yield Select[str](
                    [(t("All levels"), _ALL)], value=_ALL, allow_blank=False, id="logs-level", classes="filter"
                )
                yield Select[str](
                    [(t("All components"), _ALL)], value=_ALL, allow_blank=False, id="logs-component", classes="filter"
                )
                yield Select[int](
                    [(t("{count} lines", count=n), n) for n in LINES],
                    value=_DEFAULT_LINES,
                    allow_blank=False,
                    id="logs-lines",
                    classes="filter",
                )
            yield Static(id="logs-title")
            yield RichLog(id="logs-body", wrap=True, markup=False, highlight=False)
            with Horizontal(id="logs-buttons"):
                yield Button(t("Refresh"), id="refresh")
                yield Label(t("Follow"), id="logs-follow-label")
                yield Switch(value=False, id="logs-follow")
                yield Label(t("Record"), id="logs-record-label")
                # Until the daemon says which: the level it records at unless changed.
                yield Select[str](
                    [(t("{level} and above", level=_level(_RECORDED)), _RECORDED)],
                    value=_RECORDED,
                    allow_blank=False,
                    id="logs-record",
                )
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        options = await self._logs.options()
        self._offer(options)
        self._offer_record(options.levels, await self._logs.level())
        await self._load()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#refresh")
    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self._load()

    @on(Select.Changed, ".filter")
    @on(Switch.Changed, "#logs-follow")
    @reports_daemon_unavailable
    async def _changed(self) -> None:
        await self._load()

    @on(Select.Changed, "#logs-record")
    @reports_daemon_unavailable
    async def _record(self, event: Select.Changed) -> None:
        level = await self._logs.set_level(str(event.value))
        self.notify(t("The daemon now records {level} and above.", level=_level(level).lower()))

    def _offer(self, options: LogOptions) -> None:
        files = self.query_one("#logs-file", Select)
        with self.prevent(Select.Changed):
            files.set_options([(f.file_name, f.name) for f in options.files])
            self.query_one("#logs-level", Select).set_options(
                [(t("All levels"), _ALL), *((_level(level), level) for level in options.levels)]
            )
            self.query_one("#logs-component", Select).set_options(
                [(t("All components"), _ALL), *((c, c) for c in options.components)]
            )

    def _offer_record(self, levels: list[str], current: str) -> None:
        record = self.query_one("#logs-record", Select)
        with self.prevent(Select.Changed):
            record.set_options([(t("{level} and above", level=_level(level)), level) for level in levels])
            record.value = current

    async def _load(self) -> None:
        """While following, the stream sends the page itself."""
        self.workers.cancel_group(self, "follow")
        if self.query_one("#logs-follow", Switch).value:
            self._follow()
        else:
            self._show_page(await self._logs.page(**self._query()))

    @work(exclusive=True, group="follow")
    @reports_daemon_unavailable
    async def _follow(self) -> None:
        # Closed when the worker is cancelled, so the daemon stops sending at once.
        async with aclosing(self._logs.follow(**self._query())) as stream:
            async for item in stream:
                if isinstance(item, LogEntry):
                    self._write(item)
                else:
                    self._show_page(item)

    def _show_page(self, page: LogPage) -> None:
        self.query_one("#logs-title", Static).update(f"{page.file.file_name}  ({page.file.path})")
        body = self.query_one("#logs-body", RichLog)
        body.clear()
        for entry in page.entries:
            self._write(entry)
        if not page.entries:
            body.write(Text(t("Nothing logged that matches."), style="dim"))

    def _write(self, entry: LogEntry) -> None:
        self.query_one("#logs-body", RichLog).write(Text(log_line(entry), style=_STYLES.get(entry.level, "")))

    def _query(self) -> dict[str, Any]:
        """The picks, as `LogsApi.page` and `follow` take them. No select can be blank."""
        return {
            "name": self.query_one("#logs-file", Select).value,
            "level": self.query_one("#logs-level", Select).value,
            "component": self.query_one("#logs-component", Select).value,
            "lines": self.query_one("#logs-lines", Select).value,
        }
