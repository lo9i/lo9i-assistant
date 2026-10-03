"""Connecting email from any client, and where new mail is announced. The password never leaves the
daemon."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.integrations import email, imap
from assistant.core.integrations.email import EmailConfig, EmailError
from assistant.core.integrations.email_providers import PROVIDERS, EmailProvider

__all__ = ["EmailError", "EmailMixin", "EmailProvider", "EmailStatus"]


@dataclass
class EmailStatus:
    connected: bool
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


class EmailMixin(ServiceBase):
    def email_providers(self) -> list[EmailProvider]:
        """Providers clients offer to pick from, in display order."""
        return list(PROVIDERS)

    async def email_status(self) -> EmailStatus:
        return _status(await email.load(self._storage.store))

    async def connect_email(
        self, host: str, port: int, username: str, password: str, sender: str, imap_host: str = "", imap_port: int = 993
    ) -> EmailStatus:
        """Check the logins with the servers (IMAP too when given), then save. Raises EmailError."""
        current = await email.load(self._storage.store)
        config = EmailConfig(
            host.strip(),
            port,
            username.strip(),
            password,
            sender.strip(),
            current.allowed_recipients,
            imap_host.strip(),
            imap_port,
            current.new_mail_alerts,
        )
        await email.verify(config)
        if config.imap_host:
            await imap.verify(config)
        await email.save(self._storage.store, config)
        return _status(config)

    async def set_new_mail_alerts(self, channel: str) -> EmailStatus:
        """Announce new mail on `channel` (telegram or slack), or nowhere (""). Raises EmailError."""
        config = await email.load(self._storage.store)
        if channel not in _ALERT_CHANNELS:
            raise EmailError(f"New mail can be announced on {' or '.join(_ALERT_CHANNELS[1:])}, not {channel}.")
        if channel and not config.can_read:
            raise EmailError("Set up reading mail first: connect email again with the IMAP server.")
        config.new_mail_alerts = channel
        await email.save(self._storage.store, config)
        return _status(config)

    async def set_email_recipients(self, addresses: list[str]) -> EmailStatus:
        config = await email.load(self._storage.store)
        config.allowed_recipients = sorted({a.strip().lower() for a in addresses if a.strip()})
        await email.save(self._storage.store, config)
        return _status(config)

    async def disconnect_email(self) -> None:
        await email.clear(self._storage.store)


_ALERT_CHANNELS = ["", "telegram", "slack"]


def _status(config: EmailConfig) -> EmailStatus:
    return EmailStatus(
        config.connected,
        config.host,
        config.port,
        config.username,
        config.sender,
        config.allowed_recipients,
        config.imap_host,
        config.imap_port,
        config.new_mail_alerts,
    )
