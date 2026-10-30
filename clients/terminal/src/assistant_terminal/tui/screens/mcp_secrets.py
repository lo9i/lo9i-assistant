"""Changing an MCP server's env values (local) or headers (remote). The current values are never shown: the daemon
doesn't send them. One added by hand takes them as typed; a plugin's go over the ones it has, so what its server.yaml
sets stays."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, TextArea

from assistant.client.daemon_client import McpApi
from assistant.core.agent import McpServerChanges, McpServerError, McpServerStatus
from assistant_terminal.i18n import t
from assistant_terminal.mcp_text import parse_pairs
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class McpSecretsScreen(ModalScreen[bool]):
    """Returns True when the secrets were replaced."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", t("Close"))]

    def __init__(self, mcp: McpApi, server: McpServerStatus) -> None:
        super().__init__()
        self._mcp = mcp
        self._server = server
        self._local = bool(server.command)

    def compose(self) -> ComposeResult:
        names = ", ".join(self._server.env_keys if self._local else self._server.header_keys) or t("none")
        title = (
            t("Replace the env values of {server}", server=self._server.name)
            if self._local
            else t("Replace the headers of {server}", server=self._server.name)
        )
        how = _how(self._local, bool(self._server.source))
        with Vertical(id="mcp-secrets-dialog"):
            yield Markdown(
                f"## {title}\n\n" + t("Now set: {names}.", names=names) + f" {how}",
                id="mcp-secrets-intro",
            )
            yield TextArea(id="mcp-secrets-text")
            yield Markdown(id="mcp-secrets-message")
            with Horizontal(id="mcp-secrets-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Cancel"), id="cancel")

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


def _how(local: bool, plugin: bool) -> str:
    if plugin:
        return (
            t("One KEY=value per line; they replace the ones with the same name, and the rest stay.")
            if local
            else t("One Name: value per line; they replace the ones with the same name, and the rest stay.")
        )
    return (
        t("Type all of them, one KEY=value per line; this replaces the current ones.")
        if local
        else t("Type all of them, one Name: value per line; this replaces the current ones.")
    )
