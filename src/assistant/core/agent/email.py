"""Email accounts from any client: connect, change, pick the default, who each may email without
asking, and where its new mail is announced. Passwords never leave the daemon."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.integrations import email, imap
from assistant.core.integrations.email import EmailConfig, EmailError
from assistant.core.integrations.email_providers import PROVIDERS, EmailProvider

__all__ = ["EmailAccount", "EmailAccountNotFoundError", "EmailError", "EmailMixin", "EmailProvider"]


class EmailAccountNotFoundError(EmailError):
    pass


@dataclass
class EmailAccount:
    id: str
    label: str
    # The one tools use when the model names no account.
    default: bool
    # "ok", or "needs_sign_in" (connect it again); `problem` says why.
    status: str
    problem: str
    host: str
    port: int
    username: str
    sender: str
    allowed_recipients: list[str]
    # Reading mail: empty when only sending is set up.
    imap_host: str
    imap_port: int
    # telegram, slack, or "" (no announcements).
    new_mail_alerts: str


_ALERT_CHANNELS = ["", "telegram", "slack"]


class EmailMixin(ServiceBase):
    def email_providers(self) -> list[EmailProvider]:
        """Providers clients offer to pick from, in display order."""
        return list(PROVIDERS)

    async def email_accounts(self) -> list[EmailAccount]:
        """The default first."""
        return [_account(c) for c in await email.list_accounts(self._storage.store)]

    async def add_email_account(
        self,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> EmailAccount:
        """Check the logins with the servers (IMAP too when given), then save. The first account
        becomes the default. Raises EmailError."""
        config = EmailConfig(
            host.strip(), port, username.strip(), password, sender.strip(), [], imap_host.strip(), imap_port
        )
        config.label = label
        return await self._verified_save(config, password)

    async def update_email_account(
        self,
        account_id: str,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> EmailAccount:
        """Change an account's sign-in. An empty password keeps the saved one. Raises EmailError."""
        current = await self._email(account_id)
        if not password:
            current = await email.load(self._storage.store, self.secrets, account_id)
        config = EmailConfig(
            host.strip(),
            port,
            username.strip(),
            password or current.password,
            sender.strip(),
            current.allowed_recipients,
            imap_host.strip(),
            imap_port,
            current.new_mail_alerts,
        )
        config.account_id, config.label, config.default = account_id, label, current.default
        return await self._verified_save(config, config.password)

    async def set_default_email_account(self, account_id: str) -> EmailAccount:
        await self._email(account_id)
        await email.make_default(self._storage.store, account_id)
        return _account(await self._email(account_id))

    async def set_new_mail_alerts(self, account_id: str, channel: str) -> EmailAccount:
        """Announce the account's new mail on `channel` (telegram or slack), or nowhere (""). Raises EmailError."""
        config = await self._email(account_id)
        if channel not in _ALERT_CHANNELS:
            raise EmailError(f"New mail can be announced on {' or '.join(_ALERT_CHANNELS[1:])}, not {channel}.")
        if channel and not config.can_read:
            raise EmailError("Set up reading mail first: connect the account again with its IMAP server.")
        config.new_mail_alerts = channel
        return _account(await email.save(self._storage.store, self.secrets, config))

    async def set_email_recipients(self, account_id: str, addresses: list[str]) -> EmailAccount:
        config = await self._email(account_id)
        config.allowed_recipients = sorted({a.strip().lower() for a in addresses if a.strip()})
        return _account(await email.save(self._storage.store, self.secrets, config))

    async def remove_email_account(self, account_id: str) -> None:
        """Another account becomes the default if this one was."""
        await self._email(account_id)
        await email.remove(self._storage.store, account_id)

    async def _email(self, account_id: str) -> EmailConfig:
        """The account without its password. Raises EmailAccountNotFoundError."""
        config = await email.get(self._storage.store, account_id)
        if config is None:
            raise EmailAccountNotFoundError(f"No email account {account_id}.")
        return config

    async def _verified_save(self, config: EmailConfig, password: str) -> EmailAccount:
        await email.verify(config)
        if config.imap_host:
            await imap.verify(config)
        return _account(await email.save(self._storage.store, self.secrets, config, password))


def _account(config: EmailConfig) -> EmailAccount:
    return EmailAccount(
        config.account_id,
        config.label,
        config.default,
        config.status,
        config.problem,
        config.host,
        config.port,
        config.username,
        config.sender,
        config.allowed_recipients,
        config.imap_host,
        config.imap_port,
        config.new_mail_alerts,
    )
