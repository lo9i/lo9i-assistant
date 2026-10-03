"""Email accounts (SMTP for sending, IMAP for reading) and sending.

Each account is an account of kind "email" (core/accounts.py): its settings in the Store, its
password encrypted apart. Connected from the app (/email, Settings → Integrations), not .env.
"""

from dataclasses import dataclass, field, fields
from email.message import EmailMessage

import aiosmtplib
import certifi
from langgraph.store.base import BaseStore

from assistant.core import accounts
from assistant.core.accounts import Account, Status
from assistant.core.integrations.email_providers import imap_host_for
from assistant.core.secret_store import SecretBox, SecretError

KIND = "email"
# Where the single email setting lived before accounts; moved into the first account on start.
_LEGACY = (("integrations",), "email")
_TIMEOUT = 20
# Fields that belong to the account record or the secret, not to its settings.
_NOT_SETTINGS = {"password", "account_id", "label", "default", "status", "problem"}


class EmailError(Exception):
    pass


@dataclass
class EmailConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    # Addresses the agent may email without asking. The sender is always included.
    allowed_recipients: list[str] = field(default_factory=list)
    # Reading mail. Empty when only sending is set up. Same user name and password.
    imap_host: str = ""
    imap_port: int = 993
    # Where new mail is announced (telegram or slack), or "" for nowhere.
    new_mail_alerts: str = ""
    # The account it belongs to (core/accounts.py).
    account_id: str = ""
    label: str = ""
    default: bool = False
    status: Status = "ok"
    problem: str = ""

    @property
    def connected(self) -> bool:
        return bool(self.host and self.sender)

    @property
    def can_read(self) -> bool:
        return self.connected and bool(self.imap_host)

    def allowed(self, address: str) -> bool:
        return address.strip().lower() in {a.lower() for a in [self.sender, *self.allowed_recipients]}


async def list_accounts(store: BaseStore) -> list[EmailConfig]:
    """Every email account, the default first, without passwords."""
    return [_config(a) for a in await accounts.list_kind(store, KIND)]


async def load(store: BaseStore, box: SecretBox, name: str = "") -> EmailConfig:
    """The account called `name` (label, address or id), or the default, with its password. Not
    connected when there's no account. Raises EmailError for an unknown name, or a password that
    can't be read (the account is then marked as needing to be connected again)."""
    account = await accounts.find(store, KIND, name)
    if account is None:
        if name.strip():
            raise EmailError(await _unknown(store, name))
        return EmailConfig()
    config = _config(account)
    try:
        config.password = await accounts.secret(store, box, account)
    except SecretError as e:
        await mark_needs_sign_in(store, account.id, "Its password can't be read any more; connect it again.")
        raise EmailError(f"The password of {config.label} can't be read; connect it again in the app.") from e
    return config


async def save(store: BaseStore, box: SecretBox, config: EmailConfig, password: str = "") -> EmailConfig:
    """Saves the account (new when it has no id yet), and its password when one is given."""
    account = Account(
        id=config.account_id or accounts.new_id(),
        kind=KIND,
        label=config.label.strip() or config.sender,
        handle=config.sender,
        settings={f.name: getattr(config, f.name) for f in fields(EmailConfig) if f.name not in _NOT_SETTINGS},
        default=config.default,
        status="ok" if password else config.status,
        problem="" if password else config.problem,
    )
    await accounts.save(store, account)
    if password:
        await accounts.set_secret(store, box, account, password)
    return _config(account)


async def get(store: BaseStore, account_id: str) -> EmailConfig | None:
    """The account by id, without its password."""
    account = await accounts.get(store, KIND, account_id)
    return _config(account) if account else None


async def make_default(store: BaseStore, account_id: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        await accounts.make_default(store, account)


async def remove(store: BaseStore, account_id: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        await accounts.remove(store, account)


async def mark_needs_sign_in(store: BaseStore, account_id: str, problem: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        account.status, account.problem = "needs_sign_in", problem
        await accounts.save(store, account)


async def migrate(store: BaseStore, box: SecretBox) -> None:
    """Moves the single email setting saved before accounts into the first account."""
    item = await store.aget(*_LEGACY)
    if item is None:
        return
    legacy = EmailConfig(**{k: v for k, v in item.value.items() if k in {f.name for f in fields(EmailConfig)}})
    # Saved before reading mail existed: a provider's IMAP server is known from its SMTP server.
    if "imap_host" not in item.value:
        legacy.imap_host = imap_host_for(legacy.host)
    if legacy.connected:
        await save(store, box, legacy, legacy.password)
    await store.adelete(*_LEGACY)


def _config(account: Account) -> EmailConfig:
    known = {f.name for f in fields(EmailConfig)} - _NOT_SETTINGS
    config = EmailConfig(**{k: v for k, v in account.settings.items() if k in known})
    config.account_id, config.label, config.default = account.id, account.label, account.default
    config.status, config.problem = account.status, account.problem
    return config


async def _unknown(store: BaseStore, name: str) -> str:
    labels = [f"{c.label} <{c.sender}>" for c in await list_accounts(store)]
    known = f" The accounts are: {', '.join(labels)}." if labels else " No email account is connected."
    return f"No email account called {name!r}.{known}"


async def verify(config: EmailConfig) -> None:
    """Connect and log in without sending anything. Raises EmailError with the server's reason."""
    try:
        smtp = aiosmtplib.SMTP(**_connection(config))
        await smtp.connect()
        await smtp.login(config.username, config.password)
        await smtp.quit()
    except (aiosmtplib.SMTPException, OSError) as e:
        raise EmailError(f"Couldn't log in to {config.host}:{config.port}: {e}") from e


async def send(config: EmailConfig, to: list[str], subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = config.sender, ", ".join(to), subject
    message.set_content(body)
    try:
        await aiosmtplib.send(message, username=config.username, password=config.password, **_connection(config))
    except (aiosmtplib.SMTPException, OSError) as e:
        raise EmailError(f"Sending failed: {e}") from e


def _connection(config: EmailConfig) -> dict:
    # Port 465 uses TLS from the start; other ports (587) upgrade with STARTTLS. Certificates are
    # checked against certifi's authorities, as httpx does: Python from python.org doesn't use the
    # macOS keychain, and has none of its own until "Install Certificates.command" is run.
    tls = config.port == 465
    return {
        "hostname": config.host,
        "port": config.port,
        "use_tls": tls,
        "start_tls": not tls,
        "timeout": _TIMEOUT,
        "cert_bundle": certifi.where(),
    }
