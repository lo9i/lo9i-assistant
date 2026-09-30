"""The list of matching commands shown above the input while typing a slash command.
Up and Down move the highlight; Tab or Enter pick the highlighted command."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget

from assistant.gateways.cli.commands import COMMANDS, Command, matching

_WIDTH = max(len(c.usage) for c in COMMANDS)


class CommandMenu(Vertical):
    """One full-width row per command, so the highlight covers the whole row whatever its length."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._matches: list[Command] = []
        self._index = 0
        self._rows = {c.name: _CommandRow(c) for c in COMMANDS}

    def compose(self) -> ComposeResult:
        yield from self._rows.values()

    @property
    def open(self) -> bool:
        return bool(self._matches)

    @property
    def highlighted(self) -> Command | None:
        return self._matches[self._index] if self._matches else None

    def filter(self, text: str) -> None:
        """Show commands matching `text` while it is a slash command without arguments yet."""
        self._matches = matching(text) if text.startswith("/") and " " not in text else []
        self._index = 0
        self._render_menu()

    def move(self, step: int) -> None:
        """Move the highlight, wrapping around at either end."""
        if self._matches:
            self._index = (self._index + step) % len(self._matches)
            self._render_menu()

    def _render_menu(self) -> None:
        self.set_class(self.open, "visible")
        shown = {c.name for c in self._matches}
        highlighted = self.highlighted.name if self.highlighted else None
        for command in COMMANDS:
            row, is_highlighted = self._rows[command.name], command.name == highlighted
            row.display = command.name in shown
            row.set_class(is_highlighted, "highlighted")
            row.refresh()


class _CommandRow(Widget):
    """One command, drawn across the full row width so the highlight covers it whatever the
    description's length."""

    def __init__(self, command: Command) -> None:
        super().__init__(classes="command-row")
        self._command = command

    def render(self) -> Text:
        """Descriptions are dimmed, except on the highlighted row, where dim text is hard to read."""
        highlighted = self.has_class("highlighted")
        text = Text(f" {self._command.usage.ljust(_WIDTH)}   ")
        text.append(self._command.description, style="" if highlighted else "dim")
        text.align("left", self.size.width)
        return text
