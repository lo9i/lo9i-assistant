"""Replacing an MCP server's env values (local) or headers (remote). The current values are never
shown: the daemon doesn't send them."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, TextArea

from assistant.client.daemon_client import McpApi
from assistant.core.agent import McpServerChanges, McpServerError, McpServerStatus
from assistant_terminal.mcp_text import parse_pairs
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class McpSecretsScreen(ModalScreen[bool]):
    """Returns True when the secrets were replaced."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "Close")]

    def __init__(self, mcp: McpApi, server: McpServerStatus) -> None:
        super().__init__()
        self._mcp = mcp
        self._server = server
        self._local = bool(server.command)

    def compose(self) -> ComposeResult:
        kind, example = ("env values", "KEY=value") if self._local else ("headers", "Name: value")
        names = ", ".join(self._server.env_keys if self._local else self._server.header_keys) or "none"
        with Vertical(id="mcp-secrets-dialog"):
            yield Markdown(
                f"## Replace the {kind} of {self._server.name}\n\nNow set: {names}. "
                f"Type all of them, one {example} per line; this replaces the current ones.",
                id="mcp-secrets-intro",
            )
            yield TextArea(id="mcp-secrets-text")
            yield Markdown(id="mcp-secrets-message")
            with Horizontal(id="mcp-secrets-buttons"):
                yield Button("Save", variant="success", id="save")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        text = self.query_one("#mcp-secrets-text", TextArea).text
        try:
            pairs = parse_pairs(text, "=" if self._local else ":")
            changes = McpServerChanges(env=pairs) if self._local else McpServerChanges(headers=pairs)
            await self._mcp.change(self._server.name, changes)
        except (McpServerError, ValueError) as e:
            await self.query_one("#mcp-secrets-message", Markdown).update(f"**{e}**")
            return
        self.dismiss(True)
