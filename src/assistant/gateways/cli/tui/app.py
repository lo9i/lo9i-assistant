"""Full-screen terminal app: chat on the left, memory on the right."""

from collections.abc import Awaitable, Callable

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input

from assistant.client import DaemonClient
from assistant.core.agent import Session
from assistant.core.attachments import Attachment
from assistant.gateways.cli.commands import help_lines
from assistant.gateways.cli.files import load_attachment
from assistant.gateways.cli.tui.approval import ApprovalScreen
from assistant.gateways.cli.tui.command_menu import CommandMenu
from assistant.gateways.cli.tui.recorder import Recorder, RecordingUnavailable, available as recording_available
from assistant.gateways.cli.tui.telegram_screen import TelegramScreen
from assistant.gateways.cli.tui.turn import TurnView
from assistant.gateways.cli.tui.widgets import MemoryPanel, StatusLine, SystemNote, UserMessage

_PLACEHOLDER = "Message the assistant   (type / for commands)"
_PLACEHOLDER_WITH_MIC = "Message the assistant   (type / for commands, F3 to record)"
_MIN_RECORDING_SECONDS = 0.5


class AssistantApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "lo9i assistant"
    # Use the terminal's own background and color palette instead of Textual's theme colors.
    ansi_color = True
    BINDINGS = [
        Binding("ctrl+n", "new_thread", "New conversation"),
        # Not ctrl+b: that is the prefix key of tmux and herdr.
        Binding("f2", "toggle_memory", "Memory panel"),
        Binding("f3", "toggle_recording", "Record voice"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("tab", "complete_command", show=False, priority=True),
    ]

    def __init__(self, service: DaemonClient, session: Session) -> None:
        super().__init__()
        self._service = service
        self._session = session
        self._attachments: list[Attachment] = []
        self._busy = False
        self._recorder = Recorder()
        # Recording only works on the Mac, not in Docker; F3 is hidden when it can't.
        self._can_record = recording_available()
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/new": self._command_new,
            "/attach": self._command_attach,
            "/telegram": self._command_telegram,
            "/help": self._command_help,
            "/quit": self._command_quit,
        }

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield VerticalScroll(id="chat")
            yield MemoryPanel(id="memory")
        yield StatusLine(id="status")
        yield CommandMenu(id="command-menu")
        yield Input(placeholder=_PLACEHOLDER_WITH_MIC if self._can_record else _PLACEHOLDER, id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.sub_title = self._session.thread_id
        self.query_one("#chat", VerticalScroll).anchor()
        self.query_one("#prompt", Input).focus()
        await self._refresh_memory()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hides and disables F3 when recording can't work in this session."""
        return self._can_record if action == "toggle_recording" else True

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "prompt":
            self.query_one(CommandMenu).filter(event.value)

    def action_complete_command(self) -> None:
        """Tab completes the highlighted command while the menu is open; otherwise it moves focus."""
        command = self.query_one(CommandMenu).first
        prompt = self.query_one("#prompt", Input)
        if command is None or not prompt.has_focus:
            self.screen.focus_next()
            return
        prompt.value = command.name + (" " if command.takes_argument else "")
        prompt.cursor_position = len(prompt.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "prompt":
            return
        text = event.value.strip()
        event.input.clear()
        name, _, arg = text.partition(" ")
        command = self._commands.get(name)
        if command:
            await command(arg.strip())
        elif text or self._attachments:
            await self._send(text, self._take_attachments())

    async def _send(self, text: str, attachments: list[Attachment]) -> None:
        if self._busy:
            self.notify("The assistant is still working on the last message.", severity="warning")
            return
        await self._chat.mount(UserMessage(text or _attachment_label(attachments), [a.name for a in attachments]))
        self._run_turn(text, attachments)

    def _take_attachments(self) -> list[Attachment]:
        attachments, self._attachments = self._attachments, []
        return attachments

    @work(exclusive=True, group="turn")
    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        self._busy = True
        try:
            view = TurnView(self._chat, self._status)
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

    async def action_toggle_recording(self) -> None:
        if self._recorder.recording:
            await self._finish_recording()
            return
        if self._busy:
            self.notify("Wait for the current reply first.", severity="warning")
            return
        try:
            self._recorder.start()
        except RecordingUnavailable as e:
            self.notify(str(e), severity="error")
            return
        self._status.show("Recording, F3 to send")

    async def _finish_recording(self) -> None:
        audio, seconds = self._recorder.stop()
        self._status.clear()
        if seconds < _MIN_RECORDING_SECONDS:
            self.notify("Recording too short, nothing sent.", severity="warning")
            return
        await self._send("", [Attachment(name="recording.wav", media_type="audio/wav", data=audio)])

    @property
    def _status(self) -> StatusLine:
        return self.query_one("#status", StatusLine)

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

    async def _command_help(self, _: str) -> None:
        keys = ["F2 memory panel", "F3 record voice", "Ctrl+N new conversation", "Ctrl+Q quit"]
        body = "\n".join(help_lines())
        await self._chat.mount(SystemNote(f"## Commands\n\n```\n{body}\n```\n\n**Keys:** {', '.join(keys)}"))

    async def _command_telegram(self, _: str) -> None:
        self.push_screen(TelegramScreen(self._service))

    async def _command_quit(self, _: str) -> None:
        self.exit()


def _attachment_label(attachments: list[Attachment]) -> str:
    return "🎤 voice message" if any(a.media_type.startswith("audio/") for a in attachments) else "(attachment)"
