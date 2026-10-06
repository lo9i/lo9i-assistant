"""Full-screen terminal app: chat on the left, memory on the right."""

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input

from assistant.client import DaemonClient, DaemonUnavailableError, clipboard
from assistant.client.daemon_client import offered_plugin
from assistant.client.files import load_attachment
from assistant.client.live import LiveConversation
from assistant.client.recorder import Recorder, RecordingUnavailableError
from assistant.client.recorder import available as recording_available
from assistant.core.agent import (
    Agent,
    ConversationError,
    FoundServer,
    HandoffError,
    InvalidNameError,
    Session,
    SkillError,
)
from assistant.core.attachments import Attachment
from assistant.core.events import is_plugin_offer, is_plugin_setup, is_question, is_side_conversation
from assistant_terminal.commands import GET_TO_KNOW_ME, Command, agent_commands, help_lines
from assistant_terminal.history import History
from assistant_terminal.preferences import Preferences
from assistant_terminal.tui.attachments import AttachmentBar
from assistant_terminal.tui.command_menu import CommandMenu
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.history import show_history
from assistant_terminal.tui.live import handlers as live_handlers
from assistant_terminal.tui.mouse import switch_mouse
from assistant_terminal.tui.plugin_updates import PluginUpdates
from assistant_terminal.tui.prompt import PromptInput
from assistant_terminal.tui.screens import (
    AgentFolderScreen,
    ApprovalScreen,
    AudioScreen,
    ChannelSetupScreen,
    ConversationsScreen,
    DevicesScreen,
    EmailRecipientsScreen,
    EmailScreen,
    FilesScreen,
    JobsScreen,
    McpScreen,
    ModelScreen,
    PluginsScreen,
    ProfileScreen,
    QuestionScreen,
    RepositoryInstallScreen,
    SessionsScreen,
    SideConversationScreen,
    SkillsScreen,
    StartupScreen,
    UsageScreen,
    WebSearchScreen,
)
from assistant_terminal.tui.theme import NAME as THEME_NAME
from assistant_terminal.tui.theme import THEME
from assistant_terminal.tui.turn import TurnView
from assistant_terminal.tui.widgets import MemoryPanel, MouseStatus, StatusLine, SystemNote, UserMessage

_PLACEHOLDER = "Message the assistant   (type / for commands)"
_PLACEHOLDER_WITH_MIC = "Message the assistant   (type / for commands, F3 to record)"
_MIN_RECORDING_SECONDS = 0.5
# The title when the user hasn't named the assistant.
_DEFAULT_TITLE = "lo9i assistant"


class AssistantApp(App):
    CSS_PATH = "app.tcss"
    # The / command menu covers what the palette would; its footer spot shows the mouse state.
    ENABLE_COMMAND_PALETTE = False
    TITLE = _DEFAULT_TITLE
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+n", "new_thread", "New conversation"),
        # Not ctrl+b: that is the prefix key of tmux and herdr.
        Binding("f2", "toggle_memory", "Memory panel"),
        Binding("f3", "toggle_recording", "Record voice"),
        # Priority, so it runs before the message box's own Ctrl+V, which pastes only text copied
        # inside the app.
        Binding("ctrl+v", "paste", "Paste", show=False, priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "stop", "Stop", show=False),
        # Priority, so it runs before the message box's own Backspace; only when the box is empty.
        Binding("backspace", "remove_attachment", show=False, priority=True),
        Binding("tab", "complete_command", show=False, priority=True),
        Binding("up", "arrow(-1)", show=False, priority=True),
        Binding("down", "arrow(1)", show=False, priority=True),
    ]

    def __init__(self, service: DaemonClient, session: Session, history: History, preferences: Preferences) -> None:
        super().__init__()
        # Use the terminal's own background and color palette instead of Textual's theme colors.
        self.ansi_color = True
        self._service = service
        self._live = LiveConversation(service, session, service.clients.own_id)
        self._history = history
        self._preferences = preferences
        self._busy = False
        self._recorder = Recorder()
        # F3 is hidden when this session has no microphone (see client/recorder.py).
        self._can_record = recording_available()
        self._can_paste = clipboard.available()
        # The commands installed plugins' agents add, like /claude (refresh_agents).
        self._agent_commands: list[Command] = []
        self._agents: dict[str, Agent] = {}
        self._plugin_updates = PluginUpdates(service.repositories, lambda text: self.notify(text, timeout=10))
        self._commands: dict[str, Callable[[str], Awaitable[None]]] = {
            "/new": self._command_new,
            "/home": self._command_home,
            "/conversations": self._command_conversations,
            "/attach": self._command_attach,
            "/mcp": self._command_mcp,
            "/model": self._command_model,
            "/audio": self._command_audio,
            "/websearch": self._command_web_search,
            "/email": self._command_email,
            "/startup": self._command_startup,
            "/skills": self._command_skills,
            "/plugins": self._command_plugins,
            "/jobs": self._command_jobs,
            "/devices": self._command_devices,
            "/files": self._command_files,
            "/usage": self._command_usage,
            "/profile": self._command_profile,
            "/sessions": self._command_sessions,
            "/name": self._command_name,
            "/pin": self._command_pin,
            "/unpin": self._command_unpin,
            "/get-to-know-me": self._command_get_to_know_me,
            "/mouse": self._command_mouse,
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
        # One bordered box: the attached files, then the text being typed.
        with Horizontal(id="prompt-box"):
            yield AttachmentBar(id="attachments")
            yield PromptInput(placeholder=_PLACEHOLDER_WITH_MIC if self._can_record else _PLACEHOLDER, id="prompt")
        with Horizontal(id="footer-row"):
            yield Footer()
            yield MouseStatus(self._preferences.mouse)

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = THEME_NAME
        await self.refresh_thread()
        self.query_one("#chat", VerticalScroll).anchor()
        self.query_one("#prompt", Input).focus()
        await self.refresh_memory()
        await self.refresh_title()
        await self.refresh_plugin_updates()
        await self.refresh_agents()
        self._listen()

    @work(exclusive=True, group="events")
    async def _listen(self) -> None:
        """Daemon events for as long as the app runs (see live.py)."""
        dispatch = live_handlers(self)
        async for kind, data in self._service.events():
            handler = dispatch.get(kind)
            result = handler(data) if handler else None
            if result is not None:
                await result

    async def reload_screen(self) -> None:
        reload = getattr(self.screen, "reload", None)
        if reload is not None:
            await reload()

    def _stop_showing_turn(self) -> None:
        """Stop showing the reply in progress; the daemon finishes it and tells us when it's done."""
        self.workers.cancel_group(self, "turn")
        self.workers.cancel_group(self, "mirror")

    def run_finished(self, run: dict[str, Any]) -> None:
        if not self._live.left_run_finished(run):
            return
        excerpt = run["reply"][:160] + ("…" if len(run["reply"]) > 160 else "")
        severity = "information" if run["status"] == "ok" else "warning"
        self.notify(f"Previous conversation finished: {excerpt or run['status']}", severity=severity, timeout=10)

    def show_job(self, job: dict[str, Any]) -> None:
        severity = "information" if job["status"] == "ok" else "warning"
        self.notify(f"Job {job['name']}: {job['status']}", severity=severity)

    def show_failing(self, failing: dict[str, Any]) -> None:
        what, where = ("MCP server", "/mcp") if failing["area"] == "mcp" else ("skill", "/skills")
        self.notify(f"The {what} {failing['name']} keeps failing: {failing['error']}. See {where}.", severity="warning")

    def show_signed_out(self, signed_out: dict[str, Any]) -> None:
        self.notify(f"The MCP server {signed_out['name']} needs you to sign in again. See /mcp.", severity="warning")

    def mirror_run(self, run: dict[str, Any]) -> None:
        """Show a run started elsewhere in this conversation (another client or channel) as it happens."""
        if self._live.started_elsewhere(run):
            self._mirror(run)

    @work(group="mirror")
    @reports_daemon_unavailable
    async def _mirror(self, run: dict[str, Any]) -> None:
        if run["text"]:
            await self._chat.mount(UserMessage(f"[{run['channel']}] {run['text']}", []))
        await TurnView(self._chat, self._status).render(self._service.follow_run(run["run_id"]))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """F3 only when recording can work; Esc only while a reply runs; Up, Down and Ctrl+V only
        in the message box (command menu, history, pasting); Backspace only in an empty message box
        with files attached. Otherwise keys reach the focused widget as usual."""
        if action == "toggle_recording":
            return self._can_record
        if action == "stop":
            return self._busy or self._mirroring()
        if action == "remove_attachment":
            return self._prompt_focused() and not self._prompt.value and bool(self._attachment_bar.pending)
        if action == "paste":
            return self._can_paste and self._prompt_focused()
        if action == "arrow":
            return self._prompt_focused()
        return True

    def _prompt_focused(self) -> bool:
        """Whether the message box has the focus now. Not `has_focus`: the main screen keeps it
        while a dialog is open over it, and the dialog's keys would be taken."""
        return self.focused is self._prompt

    @property
    def _prompt(self) -> Input:
        return self.query_one("#prompt", Input)

    def _mirroring(self) -> bool:
        return any(w.group == "mirror" and w.is_running for w in self.workers)

    @reports_daemon_unavailable
    async def action_stop(self) -> None:
        """Stop the reply in progress, wherever it was started. The daemon ends it with Cancelled,
        which every channel showing it displays."""
        await self._service.cancel(self._live.session)

    def _menu_active(self) -> bool:
        return self.query_one(CommandMenu).open and self._prompt_focused()

    def action_arrow(self, step: int) -> None:
        """Moves the command menu's highlight while it's open; otherwise walks the history."""
        if self._menu_active():
            self.query_one(CommandMenu).move(step)
            return
        prompt = self.query_one("#prompt", Input)
        entry = self._history.previous(prompt.value) if step < 0 else self._history.next()
        if entry is not None:
            prompt.value = entry
            prompt.cursor_position = len(entry)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "prompt":
            # A command recalled from history is run with Enter as it is, without the menu.
            text = "" if self._history.is_recalled(event.value) else event.value
            self.query_one(CommandMenu).filter(text)

    def action_complete_command(self) -> None:
        """Tab completes the highlighted command while the menu is open; otherwise it moves focus."""
        if not self._menu_active():
            self.screen.focus_next()
            return
        command = self.query_one(CommandMenu).highlighted
        if command is not None:
            self._complete(command)

    def _complete(self, command: Command) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.value = command.name + (" " if command.takes_argument else "")
        prompt.cursor_position = len(prompt.value)

    @reports_daemon_unavailable
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "prompt":
            return
        picked = self.query_one(CommandMenu).highlighted
        if picked is not None:
            # Enter picks the highlighted command: commands that need an argument are completed
            # so it can be typed, the rest run right away.
            if picked.takes_argument:
                self._complete(picked)
                return
            event.input.value = picked.name
        text = event.input.value.strip()
        event.input.clear()
        self._history.add(text)
        name, _, arg = text.partition(" ")
        command = self._commands.get(name)
        if command:
            await command(arg.strip())
        elif name in self._agents:
            await self._command_agent(name, arg.strip())
        elif text or self._attachment_bar.pending:
            await self._send_with_attachments(text)

    async def _send_with_attachments(self, text: str) -> None:
        """Attached files stay until the message is actually sent."""
        if await self._send(text, self._attachment_bar.pending):
            await self._attachment_bar.clear()

    async def _send(self, text: str, attachments: list[Attachment]) -> bool:
        """Returns False when a reply is still running, so nothing was sent."""
        if self._busy:
            self.notify("The assistant is still working on the last message.", severity="warning")
            return False
        await self._chat.mount(UserMessage(text or _attachment_label(attachments), [a.name for a in attachments]))
        self._run_turn(text, attachments)
        return True

    @property
    def _attachment_bar(self) -> AttachmentBar:
        return self.query_one(AttachmentBar)

    @work(exclusive=True, group="turn")
    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        self._busy = True
        try:
            carried = await self._turn(text, attachments)
            if carried is not None:
                await self._move_to_side(carried)
        except DaemonUnavailableError as e:
            self._status.clear()
            self.notify(f"{e} Your message may not have been answered.", severity="error", timeout=10)
        finally:
            self._busy = False

    async def _turn(self, text: str, attachments: list[Attachment]) -> str | None:
        """Runs the turn and returns the first message of the side conversation the user moved it to, if any."""
        view = TurnView(self._chat, self._status)
        carried: str | None = None
        approvals = await view.render(self._service.send(self._live.session, text, attachments))
        while approvals:
            decisions: dict[str, dict[str, Any]] = {}
            for approval in approvals:
                decisions[approval.interrupt_id] = decision = await self._decide(approval.request)
                if is_side_conversation(approval.request) and decision.get("moved"):
                    carried = str(approval.request.get("first_message", ""))
            approvals = await view.render(self._service.resume(self._live.session, decisions))
        await self.refresh_memory()
        return carried

    async def _move_to_side(self, first_message: str) -> None:
        """The agent's suggestion was taken: the task goes on in a side conversation, starting with its brief."""
        await self._live.start_new()
        await self.refresh_thread()
        await self._chat.remove_children()
        self.notify("Moved to a side conversation. /home goes back.")
        await self._chat.mount(UserMessage(first_message, []))
        await self._turn(first_message, [])

    async def _decide(self, request: dict[str, Any]) -> dict[str, Any]:
        """The user's answer to what the run waits for. A plugin the agent offers is installed here,
        with its tokens typed in the dialog, and the answer only says whether it was."""
        if is_plugin_offer(request):
            plugin = offered_plugin(request)
            installed = bool(
                await self.push_screen_wait(RepositoryInstallScreen(self._service.repositories, offered=plugin))
            )
            if installed and isinstance(plugin, FoundServer):
                await self._set_up(plugin)
            return {"installed": installed}
        if is_plugin_setup(request):
            plugin = offered_plugin(request)
            if isinstance(plugin, FoundServer):
                await self._set_up(plugin)
            return {"done": True}
        return await self.push_screen_wait(_screen_for(request))

    async def _set_up(self, plugin: FoundServer) -> None:
        """An installed plugin's setup, in the conversation: an email plugin's accounts, a channel's pairing."""
        if plugin.email:
            await self.push_screen_wait(
                EmailScreen(self._service.email, self._service.oauth, self._service.channels, plugin.name)
            )
        if plugin.channel:
            await self.push_screen_wait(ChannelSetupScreen(self._service.channels, plugin))

    @reports_daemon_unavailable
    async def refresh_thread(self) -> None:
        """The conversation's id under the title, then the agent it's handed to and the skills pinned to it."""
        thread_id = self._live.session.thread_id
        handoff = await self._service.conversations.agent(thread_id)
        pinned = await self._service.conversations.pinned(thread_id)
        parts = [
            thread_id,
            *([f"talking to {handoff.name} in {handoff.folder}"] if handoff else []),
            *([f"pinned: {', '.join(pinned)}"] if pinned else []),
        ]
        self.sub_title = " · ".join(parts)

    async def refresh_agents(self) -> None:
        """The commands installed plugins' agents add, like /claude."""
        agents = await self._service.conversations.agents()
        self._agent_commands = agent_commands(agents)
        self._agents = {
            f"/{a.command}": a for a in agents if any(c.name == f"/{a.command}" for c in self._agent_commands)
        }
        self.query_one(CommandMenu).set_extra(self._agent_commands)

    async def refresh_title(self) -> None:
        self.title = await self._service.identity.name() or _DEFAULT_TITLE

    @reports_daemon_unavailable
    async def refresh_plugin_updates(self) -> None:
        await self._plugin_updates.refresh()

    @reports_daemon_unavailable
    async def refresh_memory(self) -> None:
        snapshot = await self._service.memory.snapshot()
        self.query_one(MemoryPanel).show(snapshot)

    @property
    def _chat(self) -> VerticalScroll:
        return self.query_one("#chat", VerticalScroll)

    @reports_daemon_unavailable
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
        except RecordingUnavailableError as e:
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
        still_running = self._busy
        if still_running:
            self._stop_showing_turn()
        await self._live.start_new(leave_running=still_running)
        await self.refresh_thread()
        await self._chat.remove_children()
        previous = " The previous reply keeps running; you'll be notified when it's done." if still_running else ""
        self.notify(f"Started a new conversation.{previous}")

    async def _command_home(self, _: str) -> None:
        still_running = self._busy
        if still_running:
            self._stop_showing_turn()
        await self._live.go_home(leave_running=still_running)
        await self.refresh_thread()
        await show_history(self._chat, await self._service.conversations.messages(self._live.session.thread_id))
        self.notify("Back home." + (" The previous reply keeps running." if still_running else ""))

    async def _command_conversations(self, _: str) -> None:
        screen = ConversationsScreen(self._service.conversations, self._live.session.thread_id)
        self.push_screen(screen, self._resume)

    @reports_daemon_unavailable
    async def _resume(self, thread_id: str | None) -> None:
        if thread_id is None or thread_id == self._live.session.thread_id:
            return
        still_running = self._busy
        if still_running:
            self._stop_showing_turn()
        try:
            await self._live.resume(thread_id, leave_running=still_running)
        except ConversationError as e:
            self.notify(str(e), severity="error")
            return
        await self.refresh_thread()
        await show_history(self._chat, await self._service.conversations.messages(thread_id))
        self.notify("Resumed the conversation." + (" The previous reply keeps running." if still_running else ""))

    async def action_paste(self) -> None:
        """A copied file or screenshot is attached to the next message; text goes in the box."""
        try:
            pasted = await clipboard.paste()
        except (clipboard.ClipboardError, FileNotFoundError) as e:
            self.notify(str(e), severity="error")
            return
        if isinstance(pasted, str):
            self.query_one("#prompt", Input).insert_text_at_cursor(pasted)
        else:
            await self._attachment_bar.add(pasted)

    async def on_prompt_input_files_dropped(self, message: PromptInput.FilesDropped) -> None:
        for path in message.paths:
            await self._command_attach(str(path))

    async def action_remove_attachment(self) -> None:
        await self._attachment_bar.remove_last()

    async def _command_attach(self, arg: str) -> None:
        try:
            attachment = load_attachment(arg)
        except FileNotFoundError as e:
            self.notify(str(e), severity="error")
            return
        await self._attachment_bar.add(attachment)

    async def _command_mouse(self, arg: str) -> None:
        """/mouse toggles; /mouse on or off sets it. Saved for the next start either way."""
        if arg not in ("", "on", "off"):
            self.notify("Use /mouse, /mouse on or /mouse off.", severity="warning")
            return
        on = not self._preferences.mouse if not arg else arg == "on"
        self._preferences.set_mouse(on)
        status = self.query_one(MouseStatus)
        state = "on" if on else "off"
        if switch_mouse(self, on):
            status.show(on)
            self.notify(f"Mouse {state}.")
        else:
            status.show(status.active, pending=on)
            self.notify(f"Mouse {state} from the next start. Restart the app to apply it.", severity="warning")

    async def _command_name(self, arg: str) -> None:
        if not arg:
            name = await self._service.identity.name()
            self.notify(f"The assistant is called {name}." if name else "The assistant has no name yet: /name <name>.")
            return
        try:
            name = await self._service.identity.rename(arg)
        except InvalidNameError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(f"Renamed to {name}. It takes effect from your next message.")

    async def _command_pin(self, arg: str) -> None:
        thread_id = self._live.session.thread_id
        if not arg:
            pinned = await self._service.conversations.pinned(thread_id)
            self.notify(f"Pinned: {', '.join(pinned)}." if pinned else "No skills pinned: /pin <skill>.")
            return
        try:
            await self._service.conversations.pin(thread_id, arg)
        except SkillError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(f"Pinned {arg} to this conversation. It takes effect from your next message.")

    async def _command_unpin(self, arg: str) -> None:
        if not arg:
            self.notify("Which skill? /unpin <skill>.", severity="warning")
            return
        await self._service.conversations.unpin(self._live.session.thread_id, arg)
        self.notify(f"Unpinned {arg}. It takes effect from your next message.")

    async def _command_agent(self, name: str, arg: str) -> None:
        """`/claude <folder>` hands the conversation to the agent, `/claude off` back; alone it picks the folder."""
        agent = self._agents[name]
        if arg == "off":
            await self._service.conversations.take_back(self._live.session.thread_id)
            self.notify("The assistant answers again from your next message.")
            await self.refresh_thread()
        elif not arg:
            screen = AgentFolderScreen(self._service.conversations, agent.name)
            self.push_screen(screen, lambda folder: self._hand_to(agent, folder))
        else:
            await self._hand_to(agent, arg)

    @reports_daemon_unavailable
    async def _hand_to(self, agent: Agent, folder: str | None) -> None:
        if folder is None:
            return
        try:
            handoff = await self._service.conversations.hand_to(self._live.session.thread_id, agent.command, folder)
        except HandoffError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(f"{handoff.name} answers from your next message, working in {handoff.folder}.")
        await self.refresh_thread()

    async def _command_get_to_know_me(self, _: str) -> None:
        """In a conversation of its own."""
        await self._command_new("")
        await self._send(GET_TO_KNOW_ME, [])

    async def _command_help(self, _: str) -> None:
        keys = ["F2 memory panel", "F3 record voice", "Ctrl+N new conversation", "Ctrl+Q quit"]
        body = "\n".join(help_lines(self._agent_commands))
        await self._chat.mount(SystemNote(f"## Commands\n\n```\n{body}\n```\n\n**Keys:** {', '.join(keys)}"))

    async def _command_plugins(self, _: str) -> None:
        self.push_screen(
            PluginsScreen(
                self._service.repositories,
                self._service.mcp,
                self._service.skills,
                self._service.channels,
                self._service.email,
                self._service.oauth,
            )
        )

    async def _command_skills(self, _: str) -> None:
        self.push_screen(SkillsScreen(self._service.skills))

    async def _command_jobs(self, _: str) -> None:
        self.push_screen(JobsScreen(self._service.jobs))

    async def _command_devices(self, _: str) -> None:
        self.push_screen(DevicesScreen(self._service.devices))

    async def _command_files(self, _: str) -> None:
        self.push_screen(FilesScreen(self._service.files))

    async def _command_usage(self, _: str) -> None:
        self.push_screen(UsageScreen(self._service.usage))

    async def _command_profile(self, _: str) -> None:
        self.push_screen(ProfileScreen(self._service.memory))

    async def _command_sessions(self, _: str) -> None:
        self.push_screen(SessionsScreen(self._service.clients))

    async def _command_startup(self, _: str) -> None:
        self.push_screen(StartupScreen(self._service.system))

    async def _command_audio(self, _: str) -> None:
        self.push_screen(AudioScreen(self._service.speech))

    async def _command_email(self, _: str) -> None:
        """Who the assistant emails without asking: the web app's Settings → General → Email."""
        self.push_screen(EmailRecipientsScreen(self._service.email))

    async def _command_web_search(self, _: str) -> None:
        self.push_screen(WebSearchScreen(self._service.web_search))

    async def _command_model(self, _: str) -> None:
        self.push_screen(ModelScreen(self._service.model))

    async def _command_mcp(self, _: str) -> None:
        self.push_screen(McpScreen(self._service.mcp, self._service.oauth))

    async def _command_quit(self, _: str) -> None:
        self.exit()


def _attachment_label(attachments: list[Attachment]) -> str:
    return "🎤 voice message" if any(a.media_type.startswith("audio/") for a in attachments) else "(attachment)"


def _screen_for(request: dict[str, Any]) -> ApprovalScreen | QuestionScreen | SideConversationScreen:
    """What the run waits for: a question with options, a task to move to a side conversation, or an approval."""
    if is_question(request):
        return QuestionScreen(request)
    if is_side_conversation(request):
        return SideConversationScreen(request)
    return ApprovalScreen(request)
