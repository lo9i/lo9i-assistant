"""Connect email (SMTP) without leaving the app, and choose who the agent may email without asking."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import EmailApi
from assistant.core.agent import EmailError, EmailStatus
from assistant.gateways.cli.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Connect email

Sending uses your mail provider's SMTP server. For Gmail: host `smtp.gmail.com`, port `587`,
your address as user, and an **app password** (Google Account → Security → App passwords)."""

_FIELDS = [
    ("email-host", "SMTP host, e.g. smtp.gmail.com", False),
    ("email-port", "Port (587, or 465)", False),
    ("email-user", "User name (usually your address)", False),
    ("email-password", "Password or app password", True),
    ("email-sender", "Send as (your address)", False),
]


class EmailScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, email: EmailApi) -> None:
        super().__init__()
        self._email = email
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="email"):
            yield Markdown(id="email-body")
            for field_id, placeholder, secret in _FIELDS:
                yield Input(placeholder=placeholder, password=secret, id=field_id)
            yield Input(placeholder="Allowed recipients, comma-separated (you are always allowed)", id="email-allowed")
            with Horizontal(id="email-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("Save recipients", id="recipients")
                yield Button("Disconnect", variant="error", id="disconnect")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._refresh(await self._email.status())

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        await self._refresh(await self._email.status())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#connect")
    @reports_daemon_unavailable
    async def _connect(self) -> None:
        values = {field_id: self.query_one(f"#{field_id}", Input).value.strip() for field_id, _, _ in _FIELDS}
        try:
            status = await self._email.connect(
                values["email-host"],
                int(values["email-port"] or 587),
                values["email-user"],
                values["email-password"],
                values["email-sender"],
            )
            self._message = "Connected ✓ The login worked."
        except (EmailError, ValueError) as e:
            self._message = f"**{e}**"
            status = await self._email.status()
        await self._refresh(status)

    @on(Button.Pressed, "#recipients")
    @reports_daemon_unavailable
    async def _save_recipients(self) -> None:
        addresses = self.query_one("#email-allowed", Input).value.split(",")
        await self._refresh(await self._email.set_recipients(addresses))

    @on(Button.Pressed, "#disconnect")
    @reports_daemon_unavailable
    async def _disconnect(self) -> None:
        await self._email.disconnect()
        self._message = ""
        await self._refresh(await self._email.status())

    async def _refresh(self, status: EmailStatus) -> None:
        """Set up the form first and the text last, so once the text shows the new state the
        fields are ready and nothing overwrites what the user types next."""
        for field_id, _, _ in _FIELDS:
            self.query_one(f"#{field_id}").display = not status.connected
        self.query_one("#connect").display = not status.connected
        self.query_one("#email-allowed").display = status.connected
        self.query_one("#recipients").display = status.connected
        self.query_one("#disconnect").display = status.connected
        self.query_one("#email-allowed", Input).value = ", ".join(status.allowed_recipients)
        await self.query_one("#email-body", Markdown).update(_describe(status, self._message))


def _describe(status: EmailStatus, message: str) -> str:
    if not status.connected:
        return _INTRO + (f"\n\n{message}" if message else "")
    allowed = ", ".join([status.sender, *status.allowed_recipients])
    lines = [
        f"## Email: {status.sender}",
        f"Server: {status.host}:{status.port}",
        f"Sends without asking to: {allowed}",
    ]
    return "\n\n".join([*lines, message] if message else lines)
