"""Email accounts without leaving the app: connect one or more, pick the default, change a sign-in,
choose who the agent may email from each without asking, and where its new mail is announced.

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
from assistant.core.agent import EmailAccount, EmailError, EmailProvider
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Add an email account

Choose your mail provider. The assistant sends from your account and reads your mail through the
provider's servers. Connect more than one (personal, work) and pick which is the default."""

_NEW = "new"
_OTHER = "other"
# id: (placeholder, secret)
_FIELDS = {
    "email-label": ("Name for this account, like Work (optional)", False),
    "email-address": ("Your email address", False),
    "email-host": ("SMTP host", False),
    "email-port": ("Port (587, or 465)", False),
    "email-user": ("User name (usually your address)", False),
    "email-password": ("App password", True),
    "email-sender": ("Send as (your address)", False),
    "email-imap": ("IMAP host, to read mail (TLS on port 993; leave empty to only send)", False),
}
_PRESET_FIELDS = {"email-label", "email-address", "email-password"}
_OTHER_FIELDS = set(_FIELDS) - {"email-address"}
_ALERTS = [
    ("Don't announce new mail", ""),
    ("Announce new mail on Telegram", "telegram"),
    ("Announce new mail on Slack", "slack"),
]
_ACCOUNT_BUTTONS = ("#recipients", "#default", "#edit", "#remove")
_OTHER_HELP = "Most providers need an **app password** here, not your account password."


class EmailScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, email: EmailApi) -> None:
        super().__init__()
        self._email = email
        self._message = ""
        self._providers: dict[str, EmailProvider] = {}
        self._choice: str | None = None
        self._accounts: list[EmailAccount] = []
        # An account's id, or _NEW while adding one.
        self._selected = _NEW
        # Changing the selected account's sign-in.
        self._editing = False

    def compose(self) -> ComposeResult:
        with Vertical(id="email"):
            yield Select[str]([("Add an account", _NEW)], allow_blank=False, value=_NEW, id="email-account")
            yield Markdown(id="email-body")
            yield Select[str]([], prompt="Choose your provider", id="email-provider")
            yield Markdown(id="email-help")
            for field_id, (placeholder, secret) in _FIELDS.items():
                yield Input(placeholder=placeholder, password=secret, id=field_id)
            yield Input(
                placeholder="Allowed recipients, comma-separated (the account itself always is)", id="email-allowed"
            )
            yield Select[str](_ALERTS, allow_blank=False, value="", id="email-alerts")
            with Horizontal(id="email-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("Save recipients", id="recipients")
                yield Button("Make default", id="default")
                yield Button("Change sign-in", id="edit")
                yield Button("Remove", variant="error", id="remove")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        providers = await self._email.providers()
        self._providers = {p.id: p for p in providers}
        options = [(p.name, p.id) for p in providers] + [("Other (enter the server yourself)", _OTHER)]
        self.query_one("#email-provider", Select).set_options(options)
        await self._load(select=None)

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        await self._load(select=self._selected)

    @on(Select.Changed, "#email-account")
    @reports_daemon_unavailable
    async def _pick_account(self, event: Select.Changed) -> None:
        value = event.value if isinstance(event.value, str) else _NEW
        if value == self._selected:
            return
        self._selected, self._editing, self._message = value, False, ""
        self._reset_form()
        await self._refresh()

    @on(Select.Changed, "#email-provider")
    @reports_daemon_unavailable
    async def _choose(self, event: Select.Changed) -> None:
        self._choice = event.value if isinstance(event.value, str) else None
        self._message = ""
        await self._refresh()

    @on(Select.Changed, "#email-alerts")
    @reports_daemon_unavailable
    async def _alerts(self, event: Select.Changed) -> None:
        account = self._account()
        channel = event.value if isinstance(event.value, str) else ""
        if account is None or channel == account.new_mail_alerts:
            return
        await self._change(lambda: self._email.set_new_mail_alerts(account.id, channel))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#connect")
    @reports_daemon_unavailable
    async def _connect(self) -> None:
        account = self._account()
        try:
            settings = self._settings()
            if account is not None and self._editing:
                saved = await self._email.update(account.id, *settings)
            else:
                saved = await self._email.add(*settings)
            self._message = "Connected ✓ The login worked."
        except (EmailError, ValueError) as e:
            self._message = f"**{e}**"
            await self._refresh()
            return
        self._editing = False
        self._reset_form()
        await self._load(select=saved.id)

    @on(Button.Pressed, "#recipients")
    @reports_daemon_unavailable
    async def _save_recipients(self) -> None:
        account = self._account()
        if account is not None:
            addresses = self.query_one("#email-allowed", Input).value.split(",")
            await self._change(lambda: self._email.set_recipients(account.id, addresses))

    @on(Button.Pressed, "#default")
    @reports_daemon_unavailable
    async def _make_default(self) -> None:
        account = self._account()
        if account is not None:
            await self._change(lambda: self._email.make_default(account.id))

    @on(Button.Pressed, "#edit")
    @reports_daemon_unavailable
    async def _edit(self) -> None:
        self._editing, self._message = True, ""
        self._reset_form()
        await self._refresh()

    @on(Button.Pressed, "#remove")
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        account = self._account()
        if account is not None:
            await self._email.remove(account.id)
            self._message = f"Removed {account.label}."
            await self._load(select=None)

    async def _change(self, call) -> None:
        try:
            saved = await call()
            self._message = ""
        except EmailError as e:
            self._message = f"**{e}**"
            saved = None
        await self._load(select=saved.id if saved else self._selected)

    async def _load(self, select: str | None) -> None:
        """Reads the accounts and shows `select`, else the default account, else the add form."""
        self._accounts = await self._email.accounts()
        ids = {a.id for a in self._accounts}
        default = self._accounts[0].id if self._accounts else _NEW
        self._selected = select if select in ids or select == _NEW else default
        options = [(_option(a), a.id) for a in self._accounts] + [("Add an account", _NEW)]
        picker = self.query_one("#email-account", Select)
        with picker.prevent(Select.Changed):
            picker.set_options(options)
            picker.value = self._selected
        await self._refresh()

    def _reset_form(self) -> None:
        """Clears the provider and what was typed, the password included."""
        self._choice = None
        provider = self.query_one("#email-provider", Select)
        with provider.prevent(Select.Changed):
            provider.clear()
        for field_id in _FIELDS:
            self.query_one(f"#{field_id}", Input).value = ""

    def _account(self) -> EmailAccount | None:
        return next((a for a in self._accounts if a.id == self._selected), None)

    def _settings(self) -> tuple[str, str, int, str, str, str, str]:
        """label, host, port, user, password, sender, IMAP host. A provider's user and sender are the address."""
        value = {field_id: self.query_one(f"#{field_id}", Input).value.strip() for field_id in _FIELDS}
        label = value["email-label"]
        provider = self._providers.get(self._choice or "")
        if provider is not None:
            address = value["email-address"]
            return label, provider.host, provider.port, address, value["email-password"], address, provider.imap_host
        port = int(value["email-port"] or 587)
        user, password, sender = value["email-user"], value["email-password"], value["email-sender"]
        return label, value["email-host"], port, user, password, sender, value["email-imap"]

    async def _refresh(self) -> None:
        """Set up the form first and the text last, so once the text shows the new state the
        fields are ready and nothing overwrites what the user types next."""
        account = self._account()
        form = account is None or self._editing
        shown = _form_fields(self._choice, self._providers) if form else set()
        for field_id in _FIELDS:
            self.query_one(f"#{field_id}").display = field_id in shown
        self.query_one("#email-provider").display = form
        self.query_one("#email-help").display = form and self._choice is not None
        self.query_one("#connect").display = bool(shown)
        self.query_one("#email-account").display = bool(self._accounts)
        for widget_id in ("#email-allowed", *_ACCOUNT_BUTTONS):
            self.query_one(widget_id).display = account is not None and not self._editing
        self.query_one("#default").display = account is not None and not self._editing and not account.default
        self.query_one("#email-alerts").display = account is not None and not self._editing and bool(account.imap_host)
        if account is not None:
            self._show_account(account)
        await self.query_one("#email-help", Markdown).update(
            _help(self._providers.get(self._choice or ""), self._editing)
        )
        await self.query_one("#email-body", Markdown).update(_describe(account, self._editing, self._message))

    def _show_account(self, account: EmailAccount) -> None:
        alerts = self.query_one("#email-alerts", Select)
        with alerts.prevent(Select.Changed):
            alerts.value = account.new_mail_alerts
        self.query_one("#email-allowed", Input).value = ", ".join(account.allowed_recipients)
        if self._editing and not self.query_one("#email-label", Input).value:
            self.query_one("#email-label", Input).value = account.label


def _option(account: EmailAccount) -> str:
    default = " (default)" if account.default else ""
    attention = " ⚠" if account.status != "ok" else ""
    return f"{account.label} <{account.sender}>{default}{attention}"


def _form_fields(choice: str | None, providers: dict[str, EmailProvider]) -> set[str]:
    if choice == _OTHER:
        return _OTHER_FIELDS
    provider = providers.get(choice or "")
    return _PRESET_FIELDS if provider is not None and provider.supported else set()


def _help(provider: EmailProvider | None, editing: bool) -> str:
    keep = "\n\nLeave the password empty to keep the saved one." if editing else ""
    if provider is None:
        return _OTHER_HELP + keep
    link = f"\n\nCreate it at {provider.password_url}" if provider.password_url else ""
    return provider.password_help + link + keep


def _describe(account: EmailAccount | None, editing: bool, message: str) -> str:
    if account is None:
        return _INTRO + (f"\n\n{message}" if message else "")
    if editing:
        text = f"## Change the sign-in of {account.label}\n\nChoose the provider and sign in again."
        return text + (f"\n\n{message}" if message else "")
    allowed = ", ".join([account.sender, *account.allowed_recipients])
    reads = f"Reads mail from: {account.imap_host}" if account.imap_host else "Reading mail: off (no IMAP server)"
    lines = [
        f"## Email: {account.label} <{account.sender}>" + (" · default" if account.default else ""),
        f"Server: {account.host}:{account.port}",
        reads,
        f"Sends without asking to: {allowed}",
    ]
    if account.status != "ok":
        lines.insert(1, f"**Needs signing in again:** {account.problem} Use Change sign-in.")
    return "\n\n".join([*lines, message] if message else lines)
