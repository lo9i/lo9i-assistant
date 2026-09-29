"""Full-screen terminal app: chat on the left, memory on the right."""

from collections.abc import Awaitable, Callable

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input

from assistant.core.agent import AssistantService, Session
from assistant.core.attachments import Attachment
from assistant.gateways.cli.files import load_attachment
from assistant.gateways.cli.tui.approval import ApprovalScreen
from assistant.gateways.cli.tui.turn import TurnView
from assistant.gateways.cli.tui.widgets import MemoryPanel, StatusLine, UserMessage

_PLACEHOLDER = "Message the assistant   (/attach <path>, /new, /quit)"


class AssistantApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "lo9i assistant"
    # Use the terminal's own background and color palette instead of Textual's theme colors.
    ansi_color = True
    BINDINGS = [
        Binding("ctrl+n", "new_thread", "New conversation"),
        # Not ctrl+b: that is the prefix key of tmux and herdr.
        Binding("f2", "toggle_memory", "Memory panel"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, service: AssistantService, session: Session) -> None:
        super().__init__()
        self._service = service
        self._session = session
        self._attachments: list[Attachment] = []
        self._busy = False
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/new": self._command_new,
            "/attach": self._command_attach,
            "/quit": self._command_quit,
        }

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield VerticalScroll(id="chat")
            yield MemoryPanel(id="memory")
        yield StatusLine(id="status")
        yield Input(placeholder=_PLACEHOLDER, id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.sub_title = self._session.thread_id
        self.query_one("#chat", VerticalScroll).anchor()
        self.query_one("#prompt", Input).focus()
        await self._refresh_memory()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        name, _, arg = text.partition(" ")
        command = self._commands.get(name)
        if command:
            await command(arg.strip())
        elif self._busy:
            self.notify("The assistant is still working on the last message.", severity="warning")
        else:
            await self._send(text)

    async def _send(self, text: str) -> None:
        attachments, self._attachments = self._attachments, []
        await self._chat.mount(UserMessage(text, [a.name for a in attachments]))
        self._run_turn(text, attachments)

    @work(exclusive=True, group="turn")
    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        self._busy = True
        try:
            view = TurnView(self._chat, self.query_one("#status", StatusLine))
            approvals = await view.render(self._service.send(self._session, text, attachments))
            while approvals:
                decisions = {a.interrupt_id: await self.push_screen_wait(ApprovalScreen(a.request)) for a in approvals}
                approvals = await view.render(self._service.resume(self._session, decisions))
            await self._refresh_memory()
        finally:
            self._busy = False

    async def _refresh_memory(self) -> None:
        snapshot = await self._service.memory_snapshot(self._session.user_id)
        self.query_one(MemoryPanel).show(snapshot)

    @property
    def _chat(self) -> VerticalScroll:
        return self.query_one("#chat", VerticalScroll)

    async def action_new_thread(self) -> None:
        await self._command_new("")

    def action_toggle_memory(self) -> None:
        self.query_one(MemoryPanel).toggle_class("hidden")

    async def _command_new(self, _: str) -> None:
        if self._busy:
            self.notify("Wait for the current reply first.", severity="warning")
            return
        self._session.thread_id = await self._service.new_thread(self._session.user_id)
        self.sub_title = self._session.thread_id
        await self._chat.remove_children()
        self.notify("Started a new conversation.")

    async def _command_attach(self, arg: str) -> None:
        try:
            attachment = load_attachment(arg)
        except FileNotFoundError as e:
            self.notify(str(e), severity="error")
            return
        self._attachments.append(attachment)
        self.notify(f"Attached {attachment.name}. It goes with your next message.")

    async def _command_quit(self, _: str) -> None:
        self.exit()
