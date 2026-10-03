"""Connect email without leaving the app, choose who the agent may email without asking, and where
new mail is announced.

The user picks their provider, so only the address and the password are typed; "Other" asks for
the servers too (SMTP to send, IMAP to read; without IMAP the assistant only sends).
"""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Select

from assistant.client.daemon_client import EmailApi
from assistant.core.agent import EmailError, EmailProvider, EmailStatus
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Connect email

Choose your mail provider. The assistant sends from your account and reads your mail through the
provider's servers."""

_OTHER = "other"
# id: (placeholder, secret)
_FIELDS = {
    "email-address": ("Your email address", False),
    "email-host": ("SMTP host", False),
    "email-port": ("Port (587, or 465)", False),
    "email-user": ("User name (usually your address)", False),
    "email-password": ("App password", True),
    "email-sender": ("Send as (your address)", False),
    "email-imap": ("IMAP host, to read mail (TLS on port 993; leave empty to only send)", False),
}
_PRESET_FIELDS = {"email-address", "email-password"}
_OTHER_FIELDS = {"email-host", "email-port", "email-user", "email-password", "email-sender", "email-imap"}
_ALERTS = [
    ("Don't announce new mail", ""),
    ("Announce new mail on Telegram", "telegram"),
    ("Announce new mail on Slack", "slack"),
]
_OTHER_HELP = "Most providers need an **app password** here, not your account password."


class EmailScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, email: EmailApi) -> None:
        super().__init__()
        self._email = email
        self._message = ""
        self._providers: dict[str, EmailProvider] = {}
        self._choice: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="email"):
            yield Markdown(id="email-body")
            yield Select[str]([], prompt="Choose your provider", id="email-provider")
            yield Markdown(id="email-help")
            for field_id, (placeholder, secret) in _FIELDS.items():
                yield Input(placeholder=placeholder, password=secret, id=field_id)
            yield Input(placeholder="Allowed recipients, comma-separated (you are always allowed)", id="email-allowed")
            yield Select[str](_ALERTS, allow_blank=False, value="", id="email-alerts")
            with Horizontal(id="email-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("Save recipients", id="recipients")
                yield Button("Disconnect", variant="error", id="disconnect")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        providers = await self._email.providers()
        self._providers = {p.id: p for p in providers}
        options = [(p.name, p.id) for p in providers] + [("Other (enter the server yourself)", _OTHER)]
        self.query_one("#email-provider", Select).set_options(options)
        await self._refresh(await self._email.status())

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        await self._refresh(await self._email.status())

    @on(Select.Changed, "#email-provider")
    @reports_daemon_unavailable
    async def _choose(self, event: Select.Changed) -> None:
        self._choice = event.value if isinstance(event.value, str) else None
        self._message = ""
        await self._refresh(await self._email.status())

    @on(Select.Changed, "#email-alerts")
    @reports_daemon_unavailable
    async def _alerts(self, event: Select.Changed) -> None:
        channel = event.value if isinstance(event.value, str) else ""
        status = await self._email.status()
        if channel == status.new_mail_alerts:
            return
        try:
            status = await self._email.set_new_mail_alerts(channel)
            self._message = ""
        except EmailError as e:
            self._message = f"**{e}**"
        await self._refresh(status)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#connect")
    @reports_daemon_unavailable
    async def _connect(self) -> None:
        try:
            status = await self._email.connect(*self._settings())
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

    def _settings(self) -> tuple[str, int, str, str, str, str]:
        """host, port, user, password, sender, IMAP host. A provider's user and sender are the address."""
        value = {field_id: self.query_one(f"#{field_id}", Input).value.strip() for field_id in _FIELDS}
        provider = self._providers.get(self._choice or "")
        if provider is not None:
            address = value["email-address"]
            return provider.host, provider.port, address, value["email-password"], address, provider.imap_host
        port = int(value["email-port"] or 587)
        user, password, sender = value["email-user"], value["email-password"], value["email-sender"]
        return value["email-host"], port, user, password, sender, value["email-imap"]

    async def _refresh(self, status: EmailStatus) -> None:
        """Set up the form first and the text last, so once the text shows the new state the
        fields are ready and nothing overwrites what the user types next."""
        shown = _form_fields(self._choice, self._providers) if not status.connected else set()
        for field_id in _FIELDS:
            self.query_one(f"#{field_id}").display = field_id in shown
        self.query_one("#email-provider").display = not status.connected
        self.query_one("#email-help").display = not status.connected and self._choice is not None
        self.query_one("#connect").display = bool(shown)
        for widget_id in ("#email-allowed", "#recipients", "#disconnect"):
            self.query_one(widget_id).display = status.connected
        self.query_one("#email-alerts").display = status.connected and bool(status.imap_host)
        self.query_one("#email-alerts", Select).value = status.new_mail_alerts
        self.query_one("#email-allowed", Input).value = ", ".join(status.allowed_recipients)
        await self.query_one("#email-help", Markdown).update(_help(self._providers.get(self._choice or "")))
        await self.query_one("#email-body", Markdown).update(_describe(status, self._message))


def _form_fields(choice: str | None, providers: dict[str, EmailProvider]) -> set[str]:
    if choice == _OTHER:
        return _OTHER_FIELDS
    provider = providers.get(choice or "")
    return _PRESET_FIELDS if provider is not None and provider.supported else set()


def _help(provider: EmailProvider | None) -> str:
    if provider is None:
        return _OTHER_HELP
    link = f"\n\nCreate it at {provider.password_url}" if provider.password_url else ""
    return provider.password_help + link


def _describe(status: EmailStatus, message: str) -> str:
    if not status.connected:
        return _INTRO + (f"\n\n{message}" if message else "")
    allowed = ", ".join([status.sender, *status.allowed_recipients])
    reads = f"Reads mail from: {status.imap_host}" if status.imap_host else "Reading mail: off (no IMAP server)"
    lines = [
        f"## Email: {status.sender}",
        f"Server: {status.host}:{status.port}",
        reads,
        f"Sends without asking to: {allowed}",
    ]
    return "\n\n".join([*lines, message] if message else lines)
