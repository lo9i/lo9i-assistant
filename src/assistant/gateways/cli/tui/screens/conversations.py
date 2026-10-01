"""Earlier conversations: pick one to see how it ended, then resume it. Returns the chosen
conversation's thread id, or None."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import ConversationsApi
from assistant.core.agent import Conversation
from assistant.gateways.cli.conversations_text import preview, when
from assistant.gateways.cli.tui.daemon_errors import reports_daemon_unavailable


class ConversationsScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        # Priority, so it runs before the list's own Enter, which also fires on a click: a click
        # only shows the conversation, Enter resumes it.
        Binding("enter", "resume", show=False, priority=True),
    ]

    def __init__(self, conversations: ConversationsApi, current: str) -> None:
        super().__init__()
        self._conversations = conversations
        self._current = current
        self._shown: dict[str, Conversation] = {}
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="conversations"):
            yield Static("Conversations", id="conversations-title")
            yield Static("No earlier conversations yet.", id="conversations-empty")
            with Horizontal(id="conversations-main"):
                yield OptionList(id="conversations-list")
                yield Static(classes="divider")
                with VerticalScroll(id="conversations-detail"):
                    yield Markdown(id="conversation-body")
            with Horizontal(id="conversations-buttons"):
                yield Button("Resume", variant="success", id="resume")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a conversation changes (a message anywhere updates the list)."""
        items = await self._conversations.recent()
        self._shown = {c.thread_id: c for c in items}
        options = self.query_one("#conversations-list", OptionList)
        options.clear_options()
        # Only when; the title is in the preview next to the list.
        options.add_options([Option(when(c), id=c.thread_id) for c in items])
        self.query_one("#conversations").set_class(not items, "empty")
        self.query_one("#resume").display = bool(items)
        if not items:
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else items[0].thread_id
        options.highlighted = list(self._shown).index(keep)
        options.focus()
        await self._show(keep)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None:
            await self._show(event.option.id)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Enter resumes only from the list; on a button it presses the button."""
        if action == "resume":
            return self.focused is self.query_one("#conversations-list")
        return True

    @on(Button.Pressed, "#resume")
    def action_resume(self) -> None:
        self.dismiss(self._selected)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)

    async def _show(self, thread_id: str) -> None:
        self._selected = thread_id
        conversation = self._shown[thread_id]
        self.query_one("#resume", Button).disabled = thread_id == self._current
        messages = await self._conversations.messages(thread_id)
        await self.query_one("#conversation-body", Markdown).update(preview(conversation, messages))
