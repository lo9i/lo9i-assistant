"""An email plugin's accounts, opened from /plugins: connect one or more, pick the default, change a
sign-in, where each one's new mail is announced.

An account uses one of its plugin's providers, so only the address and the password are typed; a
custom provider (the custom-email plugin) has no servers, so its accounts take the ones typed: SMTP to
send, IMAP to read (without IMAP the assistant only sends).
Google and Microsoft can sign in instead (OAuth), with the user's own OAuth app: the browser is sent
back to the daemon's web app on this computer, which finishes it, or the user pastes the address it
ended on.
"""

import webbrowser
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Select

from assistant.client.daemon_client import ChannelsApi, EmailApi, OAuthApi
from assistant.core.agent import EmailAccount, EmailError, EmailProvider, SignInError
from assistant_terminal.channels_text import title
from assistant_terminal.sign_in_text import MISSING_CODE, PASTE_HINT, REDIRECT, returned, signing_message
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Add an email account

The assistant sends from your account and reads your mail through the provider's servers. Connect
more than one (personal, work) and pick which is the default."""

_NEW = "new"
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
    "email-client-id": ("Your OAuth app's client ID", False),
    "email-client-secret": ("Your OAuth app's client secret", True),
    "email-returned": (PASTE_HINT, False),
}
_PRESET_FIELDS = {"email-label", "email-address", "email-password"}
_OAUTH_FIELDS = {"email-label", "email-address", "email-client-id", "email-client-secret"}
_SERVER_FIELDS = set(_FIELDS) - {"email-address", "email-client-id", "email-client-secret", "email-returned"}
_NO_ALERTS = ("Don't announce new mail", "")
_ACCOUNT_BUTTONS = ("#email-name", "#rename", "#default", "#edit", "#remove")


class EmailScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, email: EmailApi, oauth: OAuthApi, channels: ChannelsApi, plugin: str) -> None:
        """`plugin`: the email plugin whose accounts this shows."""
        super().__init__()
        self._email = email
        self._oauth = oauth
        self._channels = channels
        self._plugin = plugin
        # The installed chat channels, where new mail can be announced.
        self._channel_names: list[str] = []
        self._message = ""
        self._providers: dict[str, EmailProvider] = {}
        self._choice: str | None = None
        self._accounts: list[EmailAccount] = []
        self._recipients: list[str] = []
        # An account's id, or _NEW while adding one.
        self._selected = _NEW
        # Changing the selected account's sign-in.
        self._editing = False
        # A sign-in (OAuth) waiting for the browser.
        self._signing = False

    def compose(self) -> ComposeResult:
        with Vertical(id="email"):
            yield Select[str]([("Add an account", _NEW)], allow_blank=False, value=_NEW, id="email-account")
            yield Markdown(id="email-body")
            yield Select[str]([], prompt="Choose your provider", id="email-provider")
            yield Markdown(id="email-help")
            for field_id, (placeholder, secret) in _FIELDS.items():
                yield Input(placeholder=placeholder, password=secret, id=field_id)
            yield Input(placeholder="Account name, like Work", id="email-name")
            yield Select[str]([_NO_ALERTS], allow_blank=False, value="", id="email-alerts")
            with Horizontal(id="email-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("Finish", variant="success", id="finish")
                yield Button("Rename", id="rename")
                yield Button("Make default", id="default")
                yield Button("Change sign-in", id="edit")
                yield Button("Remove", variant="error", id="remove")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        providers = [p for p in await self._email.providers() if p.plugin == self._plugin]
        self._providers = {p.id: p for p in providers}
        self.query_one("#email-provider", Select).set_options([(p.name, p.id) for p in providers])
        self._choice = self._only_choice()
        await self._load(select=None)

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change: a sign-in the browser finished shows up."""
        known = {a.id for a in self._accounts}
        if self._signing:
            accounts = await self._email.accounts()
            new = next((a for a in accounts if a.id not in known), None)
            if new is not None or self._editing:
                self._signing = self._editing = False
                self._message = "Signed in ✓ The account can send and read mail."
                self._reset_form()
                await self._load(select=new.id if new else self._selected)
                return
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
        provider = self._providers.get(self._choice or "")
        if provider is not None and provider.oauth:
            await self._sign_in(provider)
            return
        account = self._account()
        try:
            settings = self._settings()
            if account is not None and self._editing:
                saved = await self._email.update(account.id, *settings)
            else:
                saved = await self._email.add(*settings, plugin=self._plugin)
            self._message = "Connected ✓ The login worked."
        except (EmailError, ValueError) as e:
            self._message = f"**{e}**"
            await self._refresh()
            return
        self._editing = False
        self._reset_form()
        await self._load(select=saved.id)

    async def _sign_in(self, provider: EmailProvider) -> None:
        """Opens the provider's sign-in page; the daemon's web app or Finish completes it."""
        value = {field_id: self.query_one(f"#{field_id}", Input).value.strip() for field_id in _FIELDS}
        account = self._account() if self._editing else None
        try:
            url = await self._email.start_sign_in(
                provider.oauth,
                value["email-client-id"],
                value["email-client-secret"],
                REDIRECT,
                value["email-address"] or (account.sender if account else ""),
                value["email-label"],
                account.id if account else "",
                self._plugin,
            )
        except EmailError as e:
            self._message = f"**{e}**"
            await self._refresh()
            return
        opened = webbrowser.open(url)
        self._signing = True
        self._message = signing_message(url, opened, "the account shows up here")
        await self._refresh()

    @on(Button.Pressed, "#finish")
    @reports_daemon_unavailable
    async def _finish(self) -> None:
        state, code = returned(self.query_one("#email-returned", Input).value)
        if not state or not code:
            self._message = MISSING_CODE
            await self._refresh()
            return
        try:
            saved = await self._oauth.finish(state, code)
        except SignInError as e:
            self._message = f"**{e}**"
            await self._refresh()
            return
        self._message = "Signed in ✓ The account can send and read mail."
        self._signing = self._editing = False
        self._reset_form()
        await self._load(select=saved.id)

    @on(Button.Pressed, "#rename")
    @reports_daemon_unavailable
    async def _rename(self) -> None:
        account = self._account()
        if account is not None:
            label = self.query_one("#email-name", Input).value
            await self._change(lambda: self._email.rename(account.id, label))

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
        self._accounts = [a for a in await self._email.accounts() if a.plugin == self._plugin]
        self._channel_names = [c.name for c in await self._channels.list()]
        self._recipients = await self._email.recipients()
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
        """Clears what was typed, the password included, and the provider, unless there's only one
        way to connect: the plugin's only provider."""
        self._choice = self._only_choice()
        provider = self.query_one("#email-provider", Select)
        with provider.prevent(Select.Changed):
            provider.clear()
        for field_id in _FIELDS:
            self.query_one(f"#{field_id}", Input).value = ""
        self._signing = False

    def _only_choice(self) -> str | None:
        return next(iter(self._providers)) if len(self._providers) == 1 else None

    def _account(self) -> EmailAccount | None:
        return next((a for a in self._accounts if a.id == self._selected), None)

    def _settings(self) -> tuple[str, str, int, str, str, str, str]:
        """label, host, port, user, password, sender, IMAP host. A provider's user and sender are the
        address; a custom provider's account takes the servers typed."""
        value = {field_id: self.query_one(f"#{field_id}", Input).value.strip() for field_id in _FIELDS}
        label = value["email-label"]
        provider = self._providers.get(self._choice or "")
        if provider is not None and not provider.custom:
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
        if self._signing:
            shown = shown | {"email-returned"}
        for field_id in _FIELDS:
            self.query_one(f"#{field_id}").display = field_id in shown
        self.query_one("#email-provider").display = form and len(self._providers) > 1
        self.query_one("#email-help").display = form and self._choice is not None
        self.query_one("#connect").display = bool(shown)
        self.query_one("#finish").display = self._signing
        oauth = self._providers.get(self._choice or "")
        self.query_one("#connect", Button).label = "Sign in" if oauth is not None and oauth.oauth else "Connect"
        self.query_one("#email-account").display = bool(self._accounts)
        for widget_id in _ACCOUNT_BUTTONS:
            self.query_one(widget_id).display = account is not None and not self._editing
        self.query_one("#default").display = account is not None and not self._editing and not account.default
        self.query_one("#email-alerts").display = account is not None and not self._editing and bool(account.imap_host)
        if account is not None:
            self._show_account(account)
        await self.query_one("#email-help", Markdown).update(
            _help(self._providers.get(self._choice or ""), self._editing)
        )
        await self.query_one("#email-body", Markdown).update(
            _describe(account, self._recipients, self._editing, self._message)
        )

    def _show_account(self, account: EmailAccount) -> None:
        alerts = self.query_one("#email-alerts", Select)
        with alerts.prevent(Select.Changed):
            alerts.set_options(_alert_options(self._channel_names, account.new_mail_alerts))
            alerts.value = account.new_mail_alerts
        self.query_one("#email-name", Input).value = account.label
        if self._editing and not self.query_one("#email-label", Input).value:
            self.query_one("#email-label", Input).value = account.label


def _alert_options(channels: list[str], current: str) -> list[tuple[str, str]]:
    """None, or an installed channel; the one set stays offered after its channel is removed."""
    names = channels if current in ("", *channels) else [*channels, current]
    return [_NO_ALERTS, *[(f"Announce new mail on {title(name)}", name) for name in names]]


def _option(account: EmailAccount) -> str:
    default = " (default)" if account.default else ""
    attention = " ⚠" if account.status != "ok" else ""
    return f"{account.label} <{account.sender}>{default}{attention}"


def _form_fields(choice: str | None, providers: dict[str, EmailProvider]) -> set[str]:
    provider = providers.get(choice or "")
    if provider is not None and provider.custom:
        return _SERVER_FIELDS
    if provider is not None and provider.oauth:
        return _OAUTH_FIELDS
    return _PRESET_FIELDS if provider is not None and provider.supported else set()


def _help(provider: EmailProvider | None, editing: bool) -> str:
    keep = "\n\nLeave the password empty to keep the saved one." if editing else ""
    if provider is None:
        return ""
    if provider.oauth:
        keep = "\n\nLeave the client ID and secret empty to keep the saved ones." if editing else ""
        where = f"\n\nSet it up at {provider.password_url}" if provider.password_url else ""
        return f"{provider.password_help}{where}\n\nRedirect URI to register: `{REDIRECT}`{keep}"
    link = f"\n\nCreate it at {provider.password_url}" if provider.password_url else ""
    return provider.password_help + link + keep


def _describe(account: EmailAccount | None, recipients: list[str], editing: bool, message: str) -> str:
    if account is None:
        return _INTRO + (f"\n\n{message}" if message else "")
    if editing:
        text = f"## Change the sign-in of {account.label}\n\nChoose the provider and sign in again."
        return text + (f"\n\n{message}" if message else "")
    allowed = ", ".join(["your accounts", *recipients])
    reads = f"Reads mail from: {account.imap_host}" if account.imap_host else "Reading mail: off (no IMAP server)"
    lines = [
        f"## Email: {account.label} <{account.sender}>" + (" · default" if account.default else ""),
        f"Server: {account.host}:{account.port}",
        reads,
        f"Sends without asking, from any account, to: {allowed}",
    ]
    if account.status != "ok":
        lines.insert(1, f"**Needs signing in again:** {account.problem} Use Change sign-in.")
    return "\n\n".join([*lines, message] if message else lines)
