"""Adding an MCP server: how to reach it, a look at its tools, then the tools the assistant gets.

Env values and headers are typed here and go straight to the daemon; the model never sees them.
"""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Markdown, Select, SelectionList, TextArea

from assistant.client.daemon_client import McpApi
from assistant.core.agent import McpServer, McpServerError, McpToolInfo
from assistant_terminal.mcp_text import parse_command, parse_pairs, selection, tool_label
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Add an MCP server

A local server is a command this computer runs (for example `npx -y @modelcontextprotocol/server-github`).
A remote server is a URL. Then look at its tools and choose which ones the assistant gets."""

_LOCAL, _REMOTE = "local", "remote"


class McpAddScreen(ModalScreen[bool]):
    """Returns True when a server was added."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "Close")]

    def __init__(self, mcp: McpApi) -> None:
        super().__init__()
        self._mcp = mcp
        self._tools: list[McpToolInfo] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="mcp-add"):
            yield Markdown(_INTRO, id="mcp-add-intro")
            yield Select([("Local command", _LOCAL), ("Remote URL", _REMOTE)], value=_LOCAL, id="mcp-kind")
            yield Input(placeholder="Name (lowercase, like github)", id="mcp-name")
            yield Input(placeholder="Command and arguments", id="mcp-command")
            yield Input(placeholder="URL (https://…)", id="mcp-url")
            yield TextArea(id="mcp-secrets")
            yield Checkbox("Trusted: run its tools without asking", id="mcp-trusted")
            yield Markdown(id="mcp-add-message")
            yield SelectionList[str](id="mcp-add-tools")
            with Horizontal(id="mcp-add-buttons"):
                yield Button("Look at tools", variant="primary", id="probe")
                yield Button("Add", variant="success", id="add")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._show_kind(_LOCAL)
        self.query_one("#mcp-add-tools").display = self.query_one("#add").display = False

    @on(Select.Changed, "#mcp-kind")
    def _kind_changed(self, event: Select.Changed) -> None:
        self._show_kind(str(event.value))

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#probe")
    @reports_daemon_unavailable
    async def _probe(self) -> None:
        try:
            self._tools = await self._mcp.probe(self._server())
        except (McpServerError, ValueError) as e:
            await self._say(f"**{e}**")
            return
        await self._show_tools()

    @on(Button.Pressed, "#add")
    @reports_daemon_unavailable
    async def _add(self) -> None:
        selected = set(self.query_one("#mcp-add-tools", SelectionList).selected)
        try:
            await self._mcp.add(self._server(*selection(self._tools, selected)))
        except (McpServerError, ValueError) as e:
            await self._say(f"**{e}**")
            return
        self.dismiss(True)

    def _server(self, include: list[str] | None = None, exclude: list[str] | None = None) -> McpServer:
        """The server as typed, with the tool selection. Raises ValueError for lines that can't be read."""
        server = McpServer(
            self.query_one("#mcp-name", Input).value.strip(),
            trusted=self.query_one("#mcp-trusted", Checkbox).value,
            include=include or [],
            exclude=exclude or [],
        )
        secrets = self.query_one("#mcp-secrets", TextArea).text
        if self._kind() == _REMOTE:
            server.url = self.query_one("#mcp-url", Input).value.strip()
            server.headers = parse_pairs(secrets, ":")
        else:
            server.command, server.args = parse_command(self.query_one("#mcp-command", Input).value)
            server.env = parse_pairs(secrets, "=")
        return server

    async def _show_tools(self) -> None:
        tools = self.query_one("#mcp-add-tools", SelectionList)
        tools.clear_options()
        tools.add_options([(tool_label(t), t.name, True) for t in self._tools])
        tools.display = self.query_one("#add").display = True
        await self._say(f"{len(self._tools)} tools. Uncheck the ones the assistant shouldn't get, then Add.")

    def _show_kind(self, kind: str) -> None:
        self.query_one("#mcp-command").display = kind == _LOCAL
        self.query_one("#mcp-url").display = kind == _REMOTE
        secrets = self.query_one("#mcp-secrets", TextArea)
        secrets.border_title = "Env, one KEY=value per line" if kind == _LOCAL else "Headers, one Name: value per line"

    def _kind(self) -> str:
        return str(self.query_one("#mcp-kind", Select).value)

    async def _say(self, text: str) -> None:
        await self.query_one("#mcp-add-message", Markdown).update(text)
