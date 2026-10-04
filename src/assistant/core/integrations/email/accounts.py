"""Email accounts: their settings, used by SMTP for sending and IMAP for reading.

Each account is an account of kind "email" (core/accounts.py): its settings in the Store, its
password encrypted apart. Connected from the app (Plugins), not .env. An account belongs to the email
plugin whose provider it was connected with (plugins.py), or to none when its servers were entered by
hand. While its plugin isn't installed and on, the account is kept but not used or listed.
"""

import time
from dataclasses import dataclass, fields

from langgraph.store.base import BaseStore

from assistant.core import accounts
from assistant.core.accounts import Account, Status
from assistant.core.integrations.email import oauth
from assistant.core.integrations.email import plugins as email_plugins
from assistant.core.integrations.email.errors import EmailError as EmailError
from assistant.core.secret_store import SecretBox, SecretError

KIND = "email"
# Fields that belong to the account record or the secret, not to its settings.
_NOT_SETTINGS = {"password", "account_id", "label", "default", "status", "problem"}


@dataclass
class EmailConfig:
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    # Reading mail. Empty when only sending is set up. Same user name and password.
    imap_host: str = ""
    imap_port: int = 993
    # The chat channel new mail is announced on, or "" for nowhere.
    new_mail_alerts: str = ""
    # "password", or "oauth": signed in with `oauth_provider` (google, microsoft), and `password`
    # holds an access token, refreshed when the account is loaded (oauth.py).
    auth: str = "password"
    oauth_provider: str = ""
    # The email plugin it belongs to, or "" for servers entered by hand.
    plugin: str = ""
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


async def list_accounts(store: BaseStore) -> list[EmailConfig]:
    """The accounts in use (their plugin is on), the default first, without passwords."""
    return [_config(a) for a in await _in_use(store)]


async def load(store: BaseStore, box: SecretBox, name: str = "") -> EmailConfig:
    """The account in use called `name` (label, address or id), or the default, with its password.
    Not connected when there's no account. Raises EmailError for an unknown name, or a password that
    can't be read (the account is then marked as needing to be connected again)."""
    account = _find(await _in_use(store), name)
    if account is None:
        if name.strip():
            raise EmailError(await _unknown(store, name))
        return EmailConfig()
    config = _config(account)
    try:
        secret = await accounts.secret(store, box, account)
    except SecretError as e:
        await mark_needs_sign_in(store, account.id, "Its password can't be read any more; connect it again.")
        raise EmailError(f"The password of {config.label} can't be read; connect it again in the app.") from e
    config.password = await _access_token(store, box, account, secret) if config.auth == "oauth" else secret
    return config


async def _access_token(store: BaseStore, box: SecretBox, account: Account, secret: str) -> str:
    """The account's access token, refreshed and saved when it's about to expire. Raises EmailError,
    marking the account as needing to sign in again, when the provider refuses."""
    tokens = oauth.Tokens.from_secret(secret)
    if not tokens.expired(time.time()):
        return tokens.access_token
    try:
        tokens = await oauth.refresh(tokens)
    except EmailError as e:
        await mark_needs_sign_in(store, account.id, f"Its sign-in stopped working ({e}); sign in again.")
        raise EmailError(f"{account.label} needs to sign in again in the app: {e}") from e
    await accounts.set_secret(store, box, account, tokens.to_secret())
    return tokens.access_token


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
    """The account in use by id, without its password."""
    return next((_config(a) for a in await _in_use(store) if a.id == account_id), None)


async def make_default(store: BaseStore, account_id: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        await accounts.make_default(store, account)


async def remove(store: BaseStore, account_id: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        await accounts.remove(store, account)


async def remove_plugin_accounts(store: BaseStore, plugin: str) -> None:
    """Removes the accounts of an email plugin, with their passwords: its data, deleted with it."""
    for account in await accounts.list_kind(store, KIND):
        if plugin and account.settings.get("plugin") == plugin:
            await accounts.remove(store, account)


async def mark_needs_sign_in(store: BaseStore, account_id: str, problem: str) -> None:
    account = await accounts.get(store, KIND, account_id)
    if account is not None:
        account.status, account.problem = "needs_sign_in", problem
        await accounts.save(store, account)


async def _in_use(store: BaseStore) -> list[Account]:
    """The accounts whose plugin is on, the default first."""
    active = await email_plugins.active(store)
    return [a for a in await accounts.list_kind(store, KIND) if a.settings.get("plugin", "") in {"", *active}]


def _find(listed: list[Account], name: str) -> Account | None:
    """The account called `name` (its id, label or address, any case), or the default for "". While
    the default isn't in use, the first account in use stands in for it."""
    wanted = name.strip().lower()
    if not wanted:
        return next((a for a in listed if a.default), listed[0] if listed else None)
    return next((a for a in listed if wanted in {a.id, a.label.lower(), a.handle.lower()}), None)


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
