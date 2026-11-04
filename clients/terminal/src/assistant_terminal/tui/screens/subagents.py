"""The conversation's background subagents (/subagents), or every conversation's (/subagents all, or A to switch): each
one's status, how long it's been at it and what it's doing, newest first, and the one highlighted's task, steps and
answer, kept current as they work. Answer opens what it waits for (an approval, a server's form); Stop stops one
working; Remove takes one that ended off the list; Open goes to the conversation one works for."""

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import ConversationsApi, SubagentsApi
from assistant.core.agent import BackgroundSubagent, SubagentError
from assistant_terminal.i18n import t, translatable
from assistant_terminal.subagents_text import conversation_titles, subagent_detail, subagent_line
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.page import PageScreen


class SubagentsScreen(PageScreen[str | None]):
    PAGE = "subagents"
    """Dismissed with the id of the conversation to open, or None."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", translatable("Close")),
        Binding("a", "switch", translatable("All / this conversation")),
    ]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"subagents", "subagent_step"})

    def __init__(
        self,
        subagents: SubagentsApi,
        conversations: ConversationsApi,
        thread_id: str,
        screen_for: Callable[[dict[str, Any]], Screen[dict[str, Any]]],
        everywhere: bool = False,
    ) -> None:
        """`screen_for`: the dialog that answers a request, as a run's are answered. `everywhere`: every
        conversation's, each named after its conversation, instead of `thread_id`'s."""
        super().__init__()
        self._subagents = subagents
        self._conversations = conversations
        self._conversation = thread_id
        self._screen_for = screen_for
        self._everywhere = everywhere
        self._shown: dict[str, BackgroundSubagent] = {}
        self._selected: str | None = None

    def compose_page(self) -> ComposeResult:
        with Vertical(id="subagents"):
            yield Static(id="subagents-title")
            yield Static(id="subagents-empty")
            with Horizontal(id="subagents-main"):
                yield OptionList(id="subagents-list")
                yield Static(classes="divider")
                with VerticalScroll(id="subagents-scroll"):
                    yield Static(id="subagents-detail", markup=False)
            with Horizontal(id="subagents-buttons"):
                yield Button(t("Answer"), variant="success", id="answer")
                yield Button(t("Stop"), variant="error", id="stop")
                yield Button(t("Remove"), id="remove")
                yield Button(t("Open its conversation"), id="open-conversation")
                yield Button(id="scope")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when one changes or takes a step."""
        self._show_scope()
        listed = await self._subagents.list("" if self._everywhere else self._conversation)
        self._shown = {s.id: s for s in listed}
        options = self.query_one("#subagents-list", OptionList)
        options.clear_options()
        options.add_options([Option(line, id=s.id) for s, line in zip(listed, await self._lines(listed), strict=True)])
        self.query_one("#subagents").set_class(not listed, "empty")
        if not listed:
            self._selected = None
            self._show_buttons(None)
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else listed[0].id
        options.highlighted = options.get_option_index(keep)
        options.focus()
        await self._select(keep)

    def _show_scope(self) -> None:
        everywhere = self._everywhere
        title = t("Background subagents in every conversation") if everywhere else t("Background subagents")
        self.query_one("#subagents-title", Static).update(title)
        self.query_one("#scope", Button).label = t("This conversation") if everywhere else t("All conversations")
        self.query_one("#subagents-empty", Static).update(
            t("None yet. The assistant sends them off for long work, to go on talking.")
            if everywhere
            else t("None in this conversation. The assistant sends them off for long work, to go on talking.")
        )

    async def _lines(self, listed: list[BackgroundSubagent]) -> list[str]:
        if not self._everywhere:
            return [subagent_line(s) for s in listed]
        titles = conversation_titles(listed, await self._conversations.recent())
        return [subagent_line(s, conversation=titles[s.thread_id]) for s in listed]

    @on(Button.Pressed, "#scope")
    @reports_daemon_unavailable
    async def action_switch(self) -> None:
        self._everywhere = not self._everywhere
        await self.reload()

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None and event.option.id != self._selected:
            await self._select(event.option.id)

    async def _select(self, subagent_id: str) -> None:
        self._selected = subagent_id
        try:
            details = await self._subagents.get(subagent_id)
        except SubagentError:
            return  # removed meanwhile: the next reload drops it
        self._shown[subagent_id] = details.subagent
        self.query_one("#subagents-detail", Static).update(subagent_detail(details.subagent, details.steps))
        self._show_buttons(details.subagent)

    def _show_buttons(self, subagent: BackgroundSubagent | None) -> None:
        self.query_one("#answer").display = bool(subagent and subagent.waiting)
        self.query_one("#stop").display = bool(subagent and not subagent.ended)
        self.query_one("#remove").display = bool(subagent and subagent.ended)
        self.query_one("#open-conversation").display = bool(subagent and subagent.thread_id != self._conversation)

    @on(Button.Pressed, "#answer")
    def _answer(self) -> None:
        subagent = self._shown.get(self._selected or "")
        if subagent is None or not subagent.waiting:
            return
        asked = subagent.waiting[0]
        self.app.push_screen(self._screen_for(asked.request), partial(self._answered, subagent.id, asked.interrupt_id))

    @reports_daemon_unavailable
    async def _answered(self, subagent_id: str, interrupt_id: str, decision: dict[str, Any] | None) -> None:
        if decision is not None and not await self._subagents.answer(subagent_id, interrupt_id, decision):
            self.notify(t("It doesn't wait for that any more."), severity="warning")

    @on(Button.Pressed, "#stop")
    @reports_daemon_unavailable
    async def _stop(self) -> None:
        await self._act(self._subagents.stop)

    @on(Button.Pressed, "#remove")
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        await self._act(self._subagents.remove)

    async def _act(self, action: Callable[[str], Awaitable[None]]) -> None:
        if self._selected is None:
            return
        try:
            await action(self._selected)
        except SubagentError as e:
            self.notify(str(e), severity="warning")
        await self.reload()

    @on(Button.Pressed, "#open-conversation")
    def _open_conversation(self) -> None:
        subagent = self._shown.get(self._selected or "")
        if subagent is not None:
            self.dismiss(subagent.thread_id)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)
