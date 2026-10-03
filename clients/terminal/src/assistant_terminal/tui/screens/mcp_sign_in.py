"""Signing in to a remote MCP server (OAuth): opens the server's sign-in page in a browser. The
browser comes back to the daemon's web app on this computer, which finishes it, or the user pastes
the address it ended on. Closes once the server is connected."""

import webbrowser
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import McpApi, OAuthApi
from assistant.core.agent import McpServerError, SignInError
from assistant_terminal.sign_in_text import MISSING_CODE, PASTE_HINT, REDIRECT, returned, signing_message
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class McpSignInScreen(ModalScreen[bool]):
    """Returns True when the server is signed in."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "Close")]

    def __init__(self, mcp: McpApi, oauth: OAuthApi, name: str) -> None:
        super().__init__()
        self._mcp = mcp
        self._oauth = oauth
        self._server = name

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp-sign-in"):
            yield Markdown(
                f"## Sign in to {self._server}\n\nAsking {self._server} for its sign-in page…", id="mcp-sign-in-body"
            )
            yield Input(placeholder=PASTE_HINT, id="mcp-returned")
            with Horizontal(id="mcp-sign-in-buttons"):
                yield Button("Finish", variant="success", id="finish")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        try:
            url = await self._mcp.start_sign_in(self._server, REDIRECT)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        opened = webbrowser.open(url)
        await self._say(signing_message(url, opened, "this closes by itself"))

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a server connects or changes: the browser finished the sign-in."""
        servers = {s.name: s for s in await self._mcp.servers()}
        if (server := servers.get(self._server)) is not None and server.status == "connected":
            self.dismiss(True)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#finish")
    @reports_daemon_unavailable
    async def _finish(self) -> None:
        state, code = returned(self.query_one("#mcp-returned", Input).value)
        if not state or not code:
            await self._say(MISSING_CODE)
            return
        try:
            await self._oauth.finish(state, code)
        except SignInError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss(True)

    async def _say(self, text: str) -> None:
        await self.query_one("#mcp-sign-in-body", Markdown).update(f"## Sign in to {self._server}\n\n{text}")
