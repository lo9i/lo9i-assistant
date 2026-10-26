"""The notifications feed: scheduled jobs' results, background work that ended and health checks, newest first.
Enter (or Open) goes to the conversation the work was started in, when it has one, opens a job's run in /jobs with
its whole reply, or a health check in /doctor; Dismiss and Clear remove them. Returns the conversation's thread id
to open, or None. Opening the screen marks them read."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import DoctorApi, JobsApi, NotificationsApi
from assistant.core.agent import Notification
from assistant_terminal.notifications_text import notification_line
from assistant_terminal.paging import Pages
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.paged_list import PagedOptionList
from assistant_terminal.tui.screens.doctor import DoctorScreen
from assistant_terminal.tui.screens.jobs import JobsScreen


class NotificationsScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("enter", "open", show=False, priority=True),
    ]

    def __init__(self, notifications: NotificationsApi, jobs: JobsApi, doctor: DoctorApi) -> None:
        super().__init__()
        self._notifications = notifications
        self._jobs = jobs
        self._doctor = doctor
        self._pages = Pages(lambda offset, limit: notifications.list(offset, limit), lambda n: n.id)
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="notifications"):
            yield Static("Notifications", id="notifications-title")
            yield Static("No notifications.", id="notifications-empty")
            yield PagedOptionList(self._pages, lambda n: Option(notification_line(n), id=n.id), id="notifications-list")
            with Horizontal(id="notifications-buttons"):
                yield Button("Open its conversation", variant="success", id="open")
                yield Button("Dismiss", id="dismiss")
                yield Button("Clear all", variant="error", id="clear")
                yield Button("Close", id="close")

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
        self._select(keep)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None:
            self._select(event.option.id)

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
            self.app.push_screen(DoctorScreen(self._doctor))

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

    def _select(self, notification_id: str) -> None:
        self._selected = notification_id
        notification = self._shown[notification_id]
        opening = self.query_one("#open", Button)
        opening.label = _opening(notification)
        opening.disabled = not (notification.thread_id or notification.job or notification.kind == "doctor")
        opening.tooltip = None if not opening.disabled else "It has nothing to open."


def _opening(notification: Notification) -> str:
    if notification.job:
        return "Open the job"
    return "Open the health check" if notification.kind == "doctor" else "Open its conversation"
