"""The list of matching commands shown above the input while typing a slash command."""

from rich.markup import escape
from textual.widgets import Static

from assistant.gateways.cli.commands import COMMANDS, Command, matching

_WIDTH = max(len(c.usage) for c in COMMANDS)


class CommandMenu(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._matches: list[Command] = []

    @property
    def first(self) -> Command | None:
        return self._matches[0] if self._matches else None

    def filter(self, text: str) -> None:
        """Show commands matching `text` while it is a slash command without arguments yet."""
        self._matches = matching(text) if text.startswith("/") and " " not in text else []
        self.set_class(bool(self._matches), "visible")
        self.update("\n".join(self._line(c, i == 0) for i, c in enumerate(self._matches)))

    @staticmethod
    def _line(command: Command, first: bool) -> str:
        padded = escape(command.usage.ljust(_WIDTH))
        usage = f"[b]{padded}[/b]" if first else padded
        hint = "   [dim](Tab)[/dim]" if first else ""
        return f"{usage}   [dim]{escape(command.description)}[/dim]{hint}"
