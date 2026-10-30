"""Full-screen terminal app: chat on the left, memory on the right."""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input

from assistant.client import DaemonClient, DaemonUnavailableError, clipboard
from assistant.client.daemon_client import offered_plugin
from assistant.client.daemon_client.conversations import OpenedConversation
from assistant.client.files import load_attachment
from assistant.client.live import LiveConversation
from assistant.client.recorder import Recorder, RecordingUnavailableError
from assistant.client.recorder import available as recording_available
from assistant.core.agent import (
    Agent,
    Conversation,
    ConversationError,
    FoundServer,
    HandoffError,
    InvalidNameError,
    LanguageError,
    Session,
    SkillError,
)
from assistant.core.attachments import Attachment
from assistant.core.events import (
    Dispatched,
    Event,
    is_plugin_offer,
    is_plugin_setup,
    is_question,
)
from assistant_terminal import i18n
from assistant_terminal.commands import GET_TO_KNOW_ME, Command, agent_commands, help_lines
from assistant_terminal.conversations_text import listed_title, when
from assistant_terminal.history import History
from assistant_terminal.i18n import t
from assistant_terminal.jobs_text import status as job_status
from assistant_terminal.preferences import Preferences
from assistant_terminal.tasks_text import task_line
from assistant_terminal.tui.attachments import AttachmentBar
from assistant_terminal.tui.command_menu import CommandMenu
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.followed import FollowedRuns
from assistant_terminal.tui.history import Loaders, show_history
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
    DoctorScreen,
    EmailRecipientsScreen,
    EmailScreen,
    FilesScreen,
    HomeScreen,
    HostScreen,
    JobsScreen,
    KeptKeysListScreen,
    LogsScreen,
    McpScreen,
    ModelScreen,
    NotificationsScreen,
    OpenConversationsScreen,
    PluginSignInScreen,
    PluginsScreen,
    ProfileScreen,
    PromptsScreen,
    QuestionScreen,
    RepositoryInstallScreen,
    SessionsScreen,
    SkillImportsScreen,
    SkillsScreen,
    StartupScreen,
    UsageScreen,
    WebSearchScreen,
)
from assistant_terminal.tui.screens.host import ending_text
from assistant_terminal.tui.theme import NAME as THEME_NAME
from assistant_terminal.tui.theme import THEME
from assistant_terminal.tui.turn import TurnView
from assistant_terminal.tui.widgets import (
    BriefNote,
    CarriedNote,
    ConnectionNote,
    ContextFuel,
    FollowUpNote,
    HeldNote,
    MemoryPanel,
    MouseStatus,
    StatusLine,
    SystemNote,
    UserMessage,
)

_PLACEHOLDER = t("Message the assistant   (type / for commands)")
_PLACEHOLDER_WITH_MIC = t("Message the assistant   (type / for commands, F3 to record)")
_MIN_RECORDING_SECONDS = 0.5
# The title when the user hasn't named the assistant.
_DEFAULT_TITLE = "lo9i assistant"
# Conversations the chat opens to, in a note that goes once a message is sent.
_LISTED = 8
_LIST_NOTE = "conversations-note"


class AssistantApp(App):
    CSS_PATH = "app.tcss"
    # The / command menu covers what the palette would; its footer spot shows the mouse state.
    ENABLE_COMMAND_PALETTE = False
    TITLE = _DEFAULT_TITLE
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+n", "new_thread", t("New conversation")),
        Binding("ctrl+o", "open_conversations", t("Open conversations")),
        # Not ctrl+b: that is the prefix key of tmux and herdr.
        Binding("f2", "toggle_memory", t("Memory panel")),
        Binding("f3", "toggle_recording", t("Record voice")),
        # Priority, so it runs before the message box's own Ctrl+V, which pastes only text copied
        # inside the app.
        Binding("ctrl+v", "paste", t("Paste"), show=False, priority=True),
        Binding("ctrl+q", "quit", t("Quit")),
        Binding("escape", "stop", t("Stop"), show=False),
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
        # The app starts on the inbox (main.py); a message there goes where it belongs.
        self._inbox_id = session.thread_id
        # The conversations shown here, in the order they were first shown, to switch between (Ctrl+O); never the inbox.
        self._opened: list[str] = []
        self._history = history
        self._preferences = preferences
        # The turn this app runs in the conversation shown (_turn_here), while one runs.
        self._turn_token: object | None = None
        # The approval or question dialog open for this conversation's run, while one is (_ask).
        self._asking: Screen[Any] | None = None
        # Whether the event stream opened once: the first time, the inbox's runs in progress are read (_listen).
        self._listened = False
        # The runs shown that this app isn't streaming itself (another app's, a channel's, the daemon's).
        self._followed_runs = FollowedRuns()
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
            "/inbox": self._command_inbox,
            "/move": self._command_move,
            "/conversations": self._command_conversations,
            "/open": self._command_open,
            "/notifications": self._command_notifications,
            "/attach": self._command_attach,
            "/mcp": self._command_mcp,
            "/model": self._command_model,
            "/audio": self._command_audio,
            "/websearch": self._command_web_search,
            "/email": self._command_email,
            "/startup": self._command_startup,
            "/host": self._command_host,
            "/skills": self._command_skills,
            "/import-skills": self._command_import_skills,
            "/plugins": self._command_plugins,
            "/jobs": self._command_jobs,
            "/devices": self._command_devices,
            "/files": self._command_files,
            "/usage": self._command_usage,
            "/logs": self._command_logs,
            "/doctor": self._command_doctor,
            "/profile": self._command_profile,
            "/sessions": self._command_sessions,
            "/keys": self._command_keys,
            "/home": self._command_home,
            "/name": self._command_name,
            "/language": self._command_language,
            "/prompt": self._command_prompt,
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
        yield ConnectionNote()
        yield StatusLine(id="status")
        yield CommandMenu(id="command-menu")
        # One bordered box: the attached files, then the text being typed.
        with Horizontal(id="prompt-box"):
            yield AttachmentBar(id="attachments")
            yield PromptInput(placeholder=_PLACEHOLDER_WITH_MIC if self._can_record else _PLACEHOLDER, id="prompt")
        with Horizontal(id="footer-row"):
            yield Footer()
            yield ContextFuel()
            yield MouseStatus(self._preferences.mouse)

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = THEME_NAME
        await self.refresh_thread()
        await self._show_conversations()
        self.query_one("#chat", VerticalScroll).anchor()
        self.query_one("#prompt", Input).focus()
        self._listen()
        await self.refresh_memory()
        await self.refresh_title()
        await self.refresh_plugin_updates()
        await self.refresh_agents()
        self._answer_pending()

    @work(exclusive=True, group="events")
    async def _listen(self) -> None:
        """Daemon events for as long as the app runs (see live.py)."""
        dispatch = live_handlers(self)
        note = self.query_one(ConnectionNote)
        async for kind, data in self._service.events(on_open=self._stream_opened, on_lost=note.lost):
            handler = dispatch.get(kind)
            result = handler(data) if handler else None
            if result is not None:
                await result

    def _stream_opened(self) -> None:
        """The first time, the inbox's runs in progress are read only now: the stream announces every run
        started after it opened, so none falls between the two. Runs it announces wait for that read."""
        self.query_one(ConnectionNote).back()
        if self._listened:
            return
        self._listened = True
        if self._live.session.thread_id != self._inbox_id:
            return  # Moved on before it opened: that conversation's opening read its runs.
        self._followed_runs.loading()
        self._read_in_progress()

    @work(group="mirror")
    @reports_daemon_unavailable
    async def _read_in_progress(self) -> None:
        """Cancelled when another conversation opens, which then says when its own runs have loaded."""
        try:
            opened = await self._service.conversations.live(self._live.session.thread_id)
        except DaemonUnavailableError:
            self._followed_runs.loaded()
            raise
        self._followed_runs.loaded()
        self._follow(opened.runs)

    async def reload_host(self) -> None:
        """The runs a restart or stop waits for changed: /host says how many are left."""
        if isinstance(self.screen, HostScreen):
            await self.screen.reload()

    def reload_screen(self, kind: str) -> None:
        """The open screen reads what the event `kind` changed again, if it shows that: each screen that reloads
        names the events it shows in `RELOADS_ON`. In the background, so the events after it (a reply shown live,
        an approval) don't wait for it; a newer reload replaces one running."""
        screen = self.screen
        reload = getattr(screen, "reload", None)
        if reload is not None and kind in getattr(screen, "RELOADS_ON", ()):
            screen.run_worker(reload, group="reload", exclusive=True)

    def _stop_showing_turn(self) -> None:
        """Leaving the conversation: stop showing everything tied to it, the reply in progress, an approval
        being answered and the runs followed. The daemon finishes them and tells us when they're done."""
        self._stop_turn()
        self.workers.cancel_group(self, "mirror")

    def _stop_turn(self) -> None:
        """The turn ends here at once: the next one isn't refused while the cancelled worker winds down, and its
        dialog goes with it (cancelling doesn't close a screen it waits on)."""
        self.workers.cancel_group(self, "turn")
        self.workers.cancel_group(self, "pending")
        self._turn_token = None
        if self._asking is not None and self.screen is self._asking:
            self._asking.dismiss()

    @property
    def _busy(self) -> bool:
        return self._turn_token is not None

    @contextmanager
    def _turn_here(self) -> Iterator[None]:
        """A turn runs until it ends or `_stop_turn`, whichever comes first."""
        token = self._turn_token = object()
        try:
            yield
        finally:
            if self._turn_token is token:
                self._turn_token = None

    def run_finished(self, run: dict[str, Any]) -> None:
        if run["thread_id"] == self._live.session.thread_id:
            # It may have stopped for an approval no one answered yet.
            self._answer_pending()
        if not self._live.left_run_finished(run):
            return
        excerpt = run["reply"][:160] + ("…" if len(run["reply"]) > 160 else "")
        severity = "information" if run["status"] == "ok" else "warning"
        self.notify(
            t("Previous conversation finished: {reply}", reply=excerpt or run["status"]), severity=severity, timeout=10
        )

    def show_job(self, job: dict[str, Any]) -> None:
        severity = "information" if job["status"] == "ok" else "warning"
        self.notify(t("Job {name}: {status}", name=job["name"], status=job_status(job["status"])), severity=severity)

    def show_background_ended(self, ended: dict[str, Any]) -> None:
        """A toast can't be opened: /notifications opens the conversation it ended in."""
        text = t("{text} (/notifications opens it)", text=ended["text"])
        self.notify(text, severity="information" if ended["ok"] else "warning", timeout=10)

    def show_failing(self, failing: dict[str, Any]) -> None:
        values = {"name": failing["name"], "error": failing["error"]}
        if failing["area"] == "mcp":
            self.notify(t("The MCP server {name} keeps failing: {error}. See /mcp.", **values), severity="warning")
        else:
            self.notify(t("The skill {name} keeps failing: {error}. See /skills.", **values), severity="warning")

    def show_ending(self, ending: dict[str, Any]) -> None:
        """Any app asked for a restart or stop, or took one back, or an update was installed (daemon/shutdown.py)."""
        restart = ending["ending"] == "restart"
        if ending.get("taken_back"):
            self.notify(
                t("The restart was cancelled: the assistant keeps running.")
                if restart
                else t("The stop was cancelled: the assistant keeps running.")
            )
            return
        said = ending_text("restarts" if restart else "stops", ending["waiting_for_runs"], ending["waiting_for_update"])
        back = t("This app reconnects when it's back.") if restart else t("Start it again on the computer it runs on.")
        self.notify(f"{said} {back}", timeout=15)

    def show_signed_out(self, signed_out: dict[str, Any]) -> None:
        self.notify(
            t("The MCP server {name} needs you to sign in again. See /mcp.", name=signed_out["name"]),
            severity="warning",
        )

    def mirror_run(self, run: dict[str, Any]) -> None:
        """Show a run started elsewhere in this conversation (another client or channel) as it happens."""
        if self._live.started_elsewhere(run):
            self._drop_answered_elsewhere()
            self._follow([run])

    def _drop_answered_elsewhere(self) -> None:
        """A run started elsewhere while this conversation's approval is asked here: another app answered it (or
        a new message went past it), so the dialog goes and its answer isn't sent; the run shows instead."""
        if self._asking is not None:
            self._stop_turn()

    @work(group="mirror")
    @reports_daemon_unavailable
    async def _follow(self, runs: list[dict[str, Any]]) -> None:
        """Shows the runs not shown yet from their start, one after another as they run, while this conversation
        is the one shown."""
        for run in await self._followed_runs.unseen(runs):
            if run["thread_id"] != self._live.session.thread_id:
                return
            await self._show_started(run)
            await TurnView(self._chat, self._status).render(self._service.follow_run(run["run_id"]))

    async def _show_started(self, run: dict[str, Any]) -> None:
        """What the run answers: what the user wrote, from where when it wasn't this app, a coding task the
        assistant wrote for its agent, or a follow-up's notice. Not what this app showed already when it was kept
        while an update installed."""
        if run.get("held") and any(note.held_id == run["held"] for note in self._chat.query(HeldNote)):
            return
        if run["text"] and run.get("brief"):
            await self._chat.mount(BriefNote(run["text"], run["brief"]))
        elif run["text"]:
            text = run["text"] if self._live.own(run) else f"[{run['channel']}] {run['text']}"
            await self._chat.mount(UserMessage(text, []))
        if run.get("notice"):
            await self._chat.mount(FollowUpNote(run["notice"]))

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
            self.notify(t("The assistant is still working on the last message."), severity="warning")
            return False
        await self._chat.query(f".{_LIST_NOTE}").remove()
        await self._chat.mount(UserMessage(text or _attachment_label(attachments), [a.name for a in attachments]))
        self._run_turn(text, attachments)
        return True

    @property
    def _attachment_bar(self) -> AttachmentBar:
        return self.query_one(AttachmentBar)

    @work(exclusive=True, group="turn")
    async def _run_turn(self, text: str, attachments: list[Attachment]) -> None:
        session = replace(self._live.session)
        with self._turn_here():
            try:
                await self._turn(session, lambda: self._service.send(session, text, attachments))
            except DaemonUnavailableError as e:
                self._status.clear()
                self.notify(f"{e} " + t("Your message may not have been answered."), severity="error", timeout=10)

    async def _turn(self, session: Session, start: Callable[[], AsyncIterator[Event]]) -> None:
        """Runs the turn from `start` in `session`'s conversation (a copy: the app's own changes when it moves to
        another), then goes where the inbox sent its message on."""
        view = TurnView(self._chat, self._status)
        approvals = await view.render(start())
        while approvals:
            decisions = {a.interrupt_id: await self._decide(a.request) for a in approvals}
            approvals = await view.render(self._service.resume(session, decisions))
        await self.refresh_memory()
        if view.dispatched is not None:
            await self._go_on(view.dispatched)

    async def _go_on(self, dispatched: Dispatched) -> None:
        """The inbox sent the message on: to the conversation it went to, or a new one, where it's sent as it
        was written. The next message goes there too; /inbox goes back."""
        if dispatched.thread_id:
            await self._open(dispatched.thread_id)
        else:
            await self._live.start_new()
            await self._chat.remove_children()
            await self.refresh_thread()
        self.notify(t("→ {title}. /inbox goes back.", title=dispatched.title))
        if dispatched.carried:
            await self._chat.mount(CarriedNote(dispatched.carried))
        if dispatched.brief:
            await self._chat.mount(BriefNote(dispatched.text, dispatched.brief))
        else:
            await self._chat.mount(UserMessage(dispatched.text, []))
        session = replace(self._live.session)
        await self._turn(
            session, lambda: self._service.send_dispatched(session, dispatched.id, dispatched.text, dispatched.brief)
        )

    async def _open(self, thread_id: str) -> None:
        await self._live.resume(thread_id)
        await self.refresh_thread()
        await self._show_history(thread_id)
        self._answer_pending()

    async def _show_history(self, thread_id: str) -> None:
        """The conversation's history up to its runs in progress, then those runs from their start, as if this app
        had been watching them."""
        conversations = self._service.conversations
        opened = await self._open_live(thread_id)
        try:
            loaders = Loaders(
                partial(conversations.tool_call, thread_id), partial(conversations.tool_call_step, thread_id)
            )
            await show_history(self._chat, opened.messages, loaders)
        finally:
            self._followed_runs.loaded()
        self._follow(opened.runs)

    async def _follow_in_progress(self) -> None:
        """The runs in progress in the inbox, which shows the list of conversations instead of its history."""
        opened = await self._open_live(self._live.session.thread_id)
        self._followed_runs.loaded()
        self._follow(opened.runs)

    async def _open_live(self, thread_id: str) -> OpenedConversation:
        """Stops showing the last conversation's runs and loads this one's; runs announced meanwhile wait for
        `loaded`."""
        self.workers.cancel_group(self, "mirror")
        self._followed_runs.loading()
        try:
            return await self._service.conversations.live(thread_id)
        except BaseException:
            self._followed_runs.loaded()
            raise

    def _answer_pending(self) -> None:
        """Asks what the conversation's run stopped for and still waits on, whoever started it (another app, a
        channel, the daemon's queued runs, this app before it restarted), and goes on with the answers as this
        app's own turn, as the web app does. Not while a turn runs here: it asks for its own run's approvals,
        and one answering already is never cancelled (a `run_finished` for its run comes while it runs)."""
        if not self._busy:
            self._ask_pending(replace(self._live.session))

    @work(exclusive=True, group="pending")
    @reports_daemon_unavailable
    async def _ask_pending(self, session: Session) -> None:
        """Only a worker still reading what waits is replaced by a newer one: the answering starts in the same
        step that finds it (`_turn_here`)."""
        waiting = await self._service.conversations.pending_approvals(session.thread_id)
        if not waiting or session.thread_id != self._live.session.thread_id or self._busy:
            return
        with self._turn_here():
            decisions = {a.interrupt_id: await self._decide(a.request) for a in waiting}
            await self._turn(session, lambda: self._service.resume(session, decisions))

    async def _decide(self, request: dict[str, Any]) -> dict[str, Any]:
        """The user's answer to what the run waits for. A plugin the agent offers is installed here,
        with its tokens typed in the dialog, and the answer only says whether it was."""
        if is_plugin_offer(request):
            plugin = offered_plugin(request)
            installed = bool(await self._ask(RepositoryInstallScreen(self._service.repositories, offered=plugin)))
            if installed and isinstance(plugin, FoundServer):
                await self._set_up(plugin)
            return {"installed": installed}
        if is_plugin_setup(request):
            plugin = offered_plugin(request)
            if isinstance(plugin, FoundServer):
                await self._set_up(plugin)
            return {"done": True}
        return await self._ask(_screen_for(request))

    async def _ask[T](self, screen: Screen[T]) -> T:
        """The dialog's answer; it goes when the run is answered elsewhere first (_drop_answered_elsewhere): an
        approval, a question, a plugin's install or setup."""
        self._asking = screen
        try:
            return await self.push_screen_wait(screen)
        finally:
            self._asking = None

    async def _set_up(self, plugin: FoundServer) -> None:
        """An installed plugin's setup, in the conversation: an email plugin's accounts, a channel's pairing, signing
        in."""
        if plugin.oauth:
            await self._ask(PluginSignInScreen(self._service.mcp, self._service.oauth, plugin.name, plugin.oauth))
        if plugin.email:
            await self._ask(EmailScreen(self._service.email, self._service.oauth, self._service.channels, plugin.name))
        if plugin.channel:
            await self._ask(ChannelSetupScreen(self._service.channels, plugin))

    @reports_daemon_unavailable
    async def refresh_thread(self) -> None:
        """The conversation's title under the app's, then the agent it's handed to, the skills pinned to it and
        the coding tasks running in the background. The conversation shown joins the open ones (Ctrl+O)."""
        thread_id = self._live.session.thread_id
        if thread_id != self._inbox_id and thread_id not in self._opened:
            self._opened.append(thread_id)
        handoff = await self._service.conversations.agent(thread_id)
        pinned = await self._service.conversations.pinned(thread_id)
        running = await self._service.tasks.running()
        parts = [
            await self._conversation_name(thread_id),
            *([t("talking to {agent} in {folder}", agent=handoff.name, folder=handoff.folder)] if handoff else []),
            *([t("pinned: {skills}", skills=", ".join(pinned))] if pinned else []),
            *(task_line(task, thread_id) for task in running),
        ]
        self.sub_title = " · ".join(parts)
        await self.refresh_context()

    async def _conversation_name(self, thread_id: str) -> str:
        """The inbox, the conversation's title, or a new one's until its first message lists it."""
        if thread_id == self._inbox_id:
            return t("inbox")
        conversation = await self._service.conversations.get(thread_id)
        return conversation.title if conversation else t("new conversation")

    @reports_daemon_unavailable
    async def refresh_context(self) -> None:
        """How full the conversation's context is: after each reply, a handoff, or moving to another one."""
        thread_id = self._live.session.thread_id
        stats = await self._service.conversations.stats(thread_id)
        if thread_id == self._live.session.thread_id:
            self.query_one(ContextFuel).show(stats)

    @reports_daemon_unavailable
    async def refresh_agents(self) -> None:
        """The commands installed plugins' agents add, like /claude."""
        agents = await self._service.conversations.agents()
        self._agent_commands = agent_commands(agents)
        self._agents = {
            f"/{a.command}": a for a in agents if any(c.name == f"/{a.command}" for c in self._agent_commands)
        }
        self.query_one(CommandMenu).set_extra(self._agent_commands)

    @reports_daemon_unavailable
    async def refresh_language(self) -> None:
        """What shows after uses it; key bindings and labels made at start keep theirs until the next one."""
        i18n.use(await self._service.language.get())

    @reports_daemon_unavailable
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
            self.notify(t("Wait for the current reply first."), severity="warning")
            return
        try:
            self._recorder.start()
        except RecordingUnavailableError as e:
            self.notify(str(e), severity="error")
            return
        self._status.show(t("Recording, F3 to send"))

    async def _finish_recording(self) -> None:
        audio, seconds = self._recorder.stop()
        self._status.clear()
        if seconds < _MIN_RECORDING_SECONDS:
            self.notify(t("Recording too short, nothing sent."), severity="warning")
            return
        await self._send("", [Attachment(name="recording.wav", media_type="audio/wav", data=audio)])

    @property
    def _status(self) -> StatusLine:
        return self.query_one("#status", StatusLine)

    async def _command_new(self, _: str) -> None:
        still_running = self._busy
        self._stop_showing_turn()
        await self._live.start_new(leave_running=still_running)
        await self.refresh_thread()
        await self._chat.remove_children()
        self.notify(
            t("Started a new conversation. The previous reply keeps running; you'll be notified when it's done.")
            if still_running
            else t("Started a new conversation.")
        )

    async def _command_inbox(self, _: str) -> None:
        """Back to the inbox, shown as the list of conversations rather than its own messages."""
        still_running = self._busy
        self._stop_showing_turn()
        await self._live.go_inbox(leave_running=still_running)
        self._inbox_id = self._live.session.thread_id
        await self.refresh_thread()
        await self._show_conversations()
        await self._follow_in_progress()
        self.notify(
            t("In the inbox: the next message goes where it belongs. The previous reply keeps running.")
            if still_running
            else t("In the inbox: the next message goes where it belongs.")
        )

    @reports_daemon_unavailable
    async def _show_conversations(self) -> None:
        """What the chat opens to: the latest conversations, newest first, instead of the inbox's own
        messages."""
        listed = [c for c in await self._service.conversations.recent() if not c.inbox][:_LISTED]
        await self._chat.remove_children()
        await self._chat.mount(SystemNote(_conversations_note(listed), classes=_LIST_NOTE))

    async def _command_move(self, _: str) -> None:
        """Asks in the inbox where the last message it sent on goes instead, and goes there."""
        if self._busy:
            self.notify(t("The assistant is still working on the last message."), severity="warning")
            return
        if self._live.session.thread_id != self._inbox_id:
            await self._command_inbox("")
        self._run_move()

    @work(exclusive=True, group="turn")
    async def _run_move(self) -> None:
        session = replace(self._live.session)
        with self._turn_here():
            try:
                await self._turn(session, lambda: self._service.move_dispatched(session))
            except DaemonUnavailableError as e:
                self._status.clear()
                self.notify(str(e), severity="error", timeout=10)

    async def _command_conversations(self, _: str) -> None:
        screen = ConversationsScreen(self._service.conversations, self._live.session.thread_id)
        self.push_screen(screen, self._resume)

    async def _command_open(self, _: str) -> None:
        screen = OpenConversationsScreen(
            self._service, self._opened, self._live.session.thread_id, self._inbox_id, self._opened.remove
        )
        self.push_screen(screen, self._resume)

    @reports_daemon_unavailable
    async def action_open_conversations(self) -> None:
        await self._command_open("")

    async def _command_notifications(self, _: str) -> None:
        screen = NotificationsScreen(self._service.notifications, self._service.jobs, self._service.doctor)
        self.push_screen(screen, self._resume)

    @reports_daemon_unavailable
    async def _resume(self, thread_id: str | None) -> None:
        if thread_id is None or thread_id == self._live.session.thread_id:
            return
        still_running = self._busy
        try:
            await self._live.resume(thread_id, leave_running=still_running)
        except ConversationError as e:
            self.notify(str(e), severity="error")
            return
        self._stop_showing_turn()
        await self.refresh_thread()
        await self._show_history(thread_id)
        self.notify(
            t("Resumed the conversation. The previous reply keeps running.")
            if still_running
            else t("Resumed the conversation.")
        )
        self._answer_pending()

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
            self.notify(t("Use /mouse, /mouse on or /mouse off."), severity="warning")
            return
        on = not self._preferences.mouse if not arg else arg == "on"
        self._preferences.set_mouse(on)
        status = self.query_one(MouseStatus)
        if switch_mouse(self, on):
            status.show(on)
            self.notify(t("Mouse on.") if on else t("Mouse off."))
        else:
            status.show(status.active, pending=on)
            later = (
                t("Mouse on from the next start. Restart the app to apply it.")
                if on
                else t("Mouse off from the next start. Restart the app to apply it.")
            )
            self.notify(later, severity="warning")

    async def _command_name(self, arg: str) -> None:
        if not arg:
            name = await self._service.identity.name()
            self.notify(
                t("The assistant is called {name}.", name=name)
                if name
                else t("The assistant has no name yet: /name <name>.")
            )
            return
        try:
            name = await self._service.identity.rename(arg)
        except InvalidNameError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(t("Renamed to {name}. It takes effect from your next message.", name=name))

    async def _command_language(self, arg: str) -> None:
        """/language says the one in use and the choices; /language es sets it, for every app."""
        if not arg:
            chosen = await self._service.language.get()
            self.notify(t("The apps' language is {language}. Choose auto, en or es: /language es.", language=chosen))
            return
        try:
            chosen = await self._service.language.set(arg)
        except LanguageError as e:
            self.notify(str(e), severity="error")
            return
        i18n.use(chosen)
        self.notify(t("Language set to {language}. Restart the app for its keys and labels.", language=chosen))

    async def _command_pin(self, arg: str) -> None:
        thread_id = self._live.session.thread_id
        if not arg:
            pinned = await self._service.conversations.pinned(thread_id)
            self.notify(
                t("Pinned: {skills}.", skills=", ".join(pinned)) if pinned else t("No skills pinned: /pin <skill>.")
            )
            return
        try:
            await self._service.conversations.pin(thread_id, arg)
        except SkillError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(t("Pinned {skill} to this conversation. It takes effect from your next message.", skill=arg))

    async def _command_unpin(self, arg: str) -> None:
        if not arg:
            self.notify(t("Which skill? /unpin <skill>."), severity="warning")
            return
        await self._service.conversations.unpin(self._live.session.thread_id, arg)
        self.notify(t("Unpinned {skill}. It takes effect from your next message.", skill=arg))

    async def _command_agent(self, name: str, arg: str) -> None:
        """`/claude <folder>` hands the conversation to the agent, `/claude off` back; alone it picks the folder."""
        agent = self._agents[name]
        if arg == "off":
            await self._service.conversations.take_back(self._live.session.thread_id)
            self.notify(t("The assistant answers again from your next message."))
            await self.refresh_thread()
        elif not arg:
            screen = AgentFolderScreen(self._service.conversations, agent.name)
            self.push_screen(screen, lambda folder: self._hand_to(agent, folder))
        else:
            await self._hand_to(agent, arg)

    @reports_daemon_unavailable
    async def _hand_to(self, agent: Agent, folder: str | None) -> None:
        """The inbox sends every message on, so in it the agent gets a new conversation."""
        if folder is None:
            return
        if self._live.session.thread_id == self._inbox_id:
            await self._command_new("")
        try:
            handoff = await self._service.conversations.hand_to(self._live.session.thread_id, agent.command, folder)
        except HandoffError as e:
            self.notify(str(e), severity="error")
            return
        self.notify(
            t("{agent} answers from your next message, working in {folder}.", agent=handoff.name, folder=handoff.folder)
        )
        await self.refresh_thread()

    async def _command_get_to_know_me(self, _: str) -> None:
        """In a conversation of its own."""
        await self._command_new("")
        await self._send(GET_TO_KNOW_ME, [])

    async def _command_help(self, _: str) -> None:
        keys = [
            t("F2 memory panel"),
            t("F3 record voice"),
            t("Ctrl+N new conversation"),
            t("Ctrl+O open conversations"),
            t("Ctrl+Q quit"),
        ]
        body = "\n".join(help_lines(self._agent_commands))
        commands, keys_label = t("Commands"), t("Keys:")
        await self._chat.mount(SystemNote(f"## {commands}\n\n```\n{body}\n```\n\n**{keys_label}** {', '.join(keys)}"))

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
        self.push_screen(SkillsScreen(self._service.skills, self._service.repositories))

    async def _command_import_skills(self, _: str) -> None:
        self.push_screen(SkillImportsScreen(self._service.skills))

    async def _command_prompt(self, _: str) -> None:
        self.push_screen(PromptsScreen(self._service.prompts))

    async def _command_jobs(self, _: str) -> None:
        self.push_screen(JobsScreen(self._service.jobs))

    async def _command_devices(self, _: str) -> None:
        self.push_screen(DevicesScreen(self._service.devices))

    async def _command_files(self, _: str) -> None:
        self.push_screen(FilesScreen(self._service.files))

    async def _command_usage(self, _: str) -> None:
        self.push_screen(UsageScreen(self._service.usage))

    async def _command_logs(self, _: str) -> None:
        self.push_screen(LogsScreen(self._service.logs))

    async def _command_doctor(self, _: str) -> None:
        self.push_screen(DoctorScreen(self._service.doctor))

    async def _command_profile(self, _: str) -> None:
        self.push_screen(ProfileScreen(self._service.memory))

    async def _command_sessions(self, _: str) -> None:
        self.push_screen(SessionsScreen(self._service.clients))

    async def _command_keys(self, _: str) -> None:
        self.push_screen(KeptKeysListScreen(self._service.repositories))

    async def _command_home(self, _: str) -> None:
        self.push_screen(HomeScreen(self._service.home, self._plugins_with_tools))

    async def _plugins_with_tools(self) -> list[str]:
        """The plugins a Home section may read: those with tools."""
        return [s.name for s in await self._service.mcp.servers() if s.transport != "none"]

    async def _command_startup(self, _: str) -> None:
        self.push_screen(StartupScreen(self._service.system))

    async def _command_host(self, _: str) -> None:
        self.push_screen(HostScreen(self._service.system))

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
        self.push_screen(McpScreen(self._service.mcp, self._service.oauth, self._service.repositories))

    async def _command_quit(self, _: str) -> None:
        self.exit()


def _attachment_label(attachments: list[Attachment]) -> str:
    return t("🎤 voice message") if any(a.media_type.startswith("audio/") for a in attachments) else t("(attachment)")


def _screen_for(request: dict[str, Any]) -> ApprovalScreen | QuestionScreen:
    """What the run waits for: a question with options, or an approval."""
    if is_question(request):
        return QuestionScreen(request)
    return ApprovalScreen(request)


def _conversations_note(listed: list[Conversation]) -> str:
    """Markdown: the conversations by title and when, and how to go on."""
    lines = [f"- **{listed_title(c)}** · {when(c)}" for c in listed]
    hint = t(
        "Write a message: it goes on in the conversation it's about, or starts a new one. "
        "/conversations opens one, /new starts one, /notifications shows what finished."
    )
    if not lines:
        return "### " + t("No conversations yet") + f"\n\n{hint}"
    return "\n".join(["### " + t("Conversations"), *lines, "", hint])
