"""The notifications feed: scheduled jobs' results, background work that ended and health checks, newest first,
each listed only by when it came, on one line, with the whole of the one picked (what it's about, all it says)
beside the list, as /conversations lays them out.
Enter (or Open) goes to the conversation the work was started in, when it has one, opens a job's run in /jobs with
its whole reply, a health check in /doctor, or Home for the briefing and a reminder; Dismiss and Clear remove them.
Returns the conversation's thread id to open, or None. Opening the screen marks them read."""

from collections.abc import Callable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from lo9i.client.daemon_client import JobsApi, NotificationsApi
from lo9i.core.agent import Notification
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.notifications_text import notified_at
from lo9i_terminal.paging import Pages
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.page import PageScreen
from lo9i_terminal.tui.paged_list import PagedOptionList
from lo9i_terminal.tui.screens.jobs import JobsScreen

# What opens Home, whose Open loops card has the loops: the briefing, and a reminder of a loop without a conversation.
_HOME = ("briefing", "reminder")


class NotificationsScreen(PageScreen[str | None]):
    PAGE = "notifications"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", translatable("Close")),
        Binding("enter", "open", show=False, priority=True),
    ]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"notifications"})

    def __init__(
        self,
        notifications: NotificationsApi,
        jobs: JobsApi,
        open_home: Callable[[], object],
        open_health: Callable[[], object],
    ) -> None:
        """`open_home` and `open_health`: have the app show Home, or Settings' health check, in this page's place,
        once this page's handler is done."""
        super().__init__()
        self._notifications = notifications
        self._jobs = jobs
        self._open_home = open_home
        self._open_health = open_health
        self._pages = Pages(lambda offset, limit: notifications.list(offset, limit), lambda n: n.id)
        self._selected: str | None = None

    def compose_page(self) -> ComposeResult:
        with Vertical(id="notifications"):
            yield Static(t("Notifications"), id="notifications-title")
            yield Static(t("No notifications."), id="notifications-empty")
            with Horizontal(id="notifications-main"):
                yield PagedOptionList(self._pages, lambda n: Option(_row(n), id=n.id), id="notifications-list")
                yield Static(classes="divider")
                with VerticalScroll(id="notifications-detail"):
                    yield Markdown(id="notifications-body")
            with Horizontal(id="notifications-buttons"):
                yield Button(t("Open its conversation"), variant="success", id="open")
                yield Button(t("Dismiss"), id="dismiss")
                yield Button(t("Clear all"), variant="error", id="clear")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()
        await self._notifications.mark_read()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the feed changes (a job ran, a task ended)."""
        options = self.query_one("#notifications-list", PagedOptionList)
        items = await options.reload()
        self.query_one("#notifications").set_class(not items, "empty")
        for button in ("#open", "#dismiss", "#clear"):
            self.query_one(button).display = bool(items)
        if not items:
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else items[0].id
        options.highlighted = options.get_option_index(keep)
        options.focus()
        await self._select(keep)

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Only for one the list still shows: a highlight can come in after Dismiss built the list again."""
        if event.option.id in self._shown:
            await self._select(event.option.id)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Enter opens only from the list; on a button it presses the button."""
        if action == "open":
            return self.focused is self.query_one("#notifications-list")
        return True

    @on(Button.Pressed, "#open")
    def action_open(self) -> None:
        notification = self._shown.get(self._selected or "")
        if notification is not None and notification.thread_id:
            self.dismiss(notification.thread_id)
        elif notification is not None and notification.job:
            self.app.push_screen(JobsScreen(self._jobs, notification.job, notification.run_at))
        elif notification is not None and notification.kind == "doctor":
            self._open_health()
        elif notification is not None and notification.kind in _HOME:
            self._open_home()

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#dismiss")
    @reports_daemon_unavailable
    async def _dismiss(self) -> None:
        if self._selected is not None:
            await self._notifications.dismiss(self._selected)
            await self.reload()

    @on(Button.Pressed, "#clear")
    @reports_daemon_unavailable
    async def _clear(self) -> None:
        await self._notifications.clear()
        await self.reload()

    @property
    def _shown(self) -> dict[str, Notification]:
        return {n.id: n for n in self._pages.items}

    async def _select(self, notification_id: str) -> None:
        self._selected = notification_id
        notification = self._shown[notification_id]
        opening = self.query_one("#open", Button)
        opening.label = _opening(notification)
        opening.disabled = not (notification.thread_id or notification.job or notification.kind in ("doctor", *_HOME))
        opening.tooltip = None if not opening.disabled else t("It has nothing to open.")
        await self.query_one("#notifications-body", Markdown).update(_detail(notification))
        self.query_one("#notifications-detail", VerticalScroll).scroll_home(animate=False)


def _row(notification: Notification) -> str:
    """When it came; what it's about shows beside the list."""
    return notified_at(notification)


def _detail(notification: Notification) -> str:
    """The whole notification, as Markdown: what it's about, when it came, and all it says."""
    return f"### {notification.title}\n\n{notified_at(notification)}\n\n{notification.text}"


def _opening(notification: Notification) -> str:
    if notification.job:
        return t("Open the job")
    if notification.kind in _HOME:
        return t("Open Home")
    return t("Open the health check") if notification.kind == "doctor" else t("Open its conversation")
