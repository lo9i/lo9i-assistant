"""The open conversations (Ctrl+O, /open): the ones opened in this app and any other with something working in it, to
switch between, as the web app's sidebar lists them under Chat (open_text.py). Returns the conversation to show, or
None. Closing one only takes it off the list; it stays in /conversations, and a reply in it keeps going."""

from collections.abc import Callable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import DaemonClient
from assistant_terminal.i18n import t, translatable
from assistant_terminal.open_text import OpenItem, line, open_list
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class OpenConversationsScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss(None)", translatable("Close")),
        # Priority, so it runs before the list's own Enter.
        Binding("enter", "switch", show=False, priority=True),
        Binding("delete,x", "close_conversation", translatable("Close it"), show=False),
    ]
    # A conversation titled or deleted, a reply or a coding task starting or ending anywhere.
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset(
        {"conversations", "run", "run_finished", "agent_task_progress", "agent_task_reports"}
    )

    def __init__(
        self, service: DaemonClient, opened: list[str], current: str, inbox: str, close: Callable[[str], None]
    ) -> None:
        """`opened`: the conversations opened in this app, in order; `close` takes one off it."""
        super().__init__()
        self._service = service
        self._opened = opened
        self._current = current
        self._inbox = inbox
        self._forget = close
        self._items: list[OpenItem] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="open-conversations"):
            yield Static(t("Open conversations"), id="open-conversations-title")
            yield Static(
                t("None open yet: /conversations opens one, /clear starts one."), id="open-conversations-empty"
            )
            yield OptionList(id="open-conversations-list")
            with Horizontal(id="open-conversations-buttons"):
                yield Button(t("Show"), variant="success", id="switch")
                yield Button(t("Close it"), id="close-conversation")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()
        self.query_one("#open-conversations-list", OptionList).focus()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        conversations = await self._service.conversations.recent()
        runs = await self._service.runs_in_progress()
        tasks = await self._service.tasks.running()
        working = {r["thread_id"] for r in runs} | {task.thread_id for task in tasks if task.thread_id}
        waiting = {i for i in self._opened if await self._service.conversations.pending_approvals(i)}
        self._items = open_list(self._opened, self._current, self._inbox, conversations, working, waiting)
        options = self.query_one("#open-conversations-list", OptionList)
        highlighted = options.highlighted
        options.clear_options()
        options.add_options([Option(line(item), id=item.thread_id) for item in self._items])
        if self._items:
            current = next((n for n, item in enumerate(self._items) if item.current), 0)
            options.highlighted = min(highlighted, len(self._items) - 1) if highlighted is not None else current
        self.query_one("#open-conversations").set_class(not self._items, "empty")
        self.query_one("#switch").display = self.query_one("#close-conversation").display = bool(self._items)

    def _highlighted(self) -> OpenItem | None:
        index = self.query_one("#open-conversations-list", OptionList).highlighted
        return self._items[index] if index is not None and index < len(self._items) else None

    @on(Button.Pressed, "#switch")
    def action_switch(self) -> None:
        item = self._highlighted()
        if item is not None:
            self.dismiss(item.thread_id)

    @on(Button.Pressed, "#close-conversation")
    @reports_daemon_unavailable
    async def action_close_conversation(self) -> None:
        item = self._highlighted()
        if item is None:
            return
        if item.current:
            self.notify(t("This one is shown: switch to another first, or /clear."), severity="warning")
            return
        if not item.opened:
            self.notify(t("It isn't open here: it shows while something works in it."), severity="warning")
            return
        self._forget(item.thread_id)
        await self.reload()

    @on(Button.Pressed, "#close")
    def _close_screen(self) -> None:
        self.dismiss(None)
