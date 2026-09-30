"""Connecting email from any client. The password never leaves the daemon."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.integrations import email
from assistant.core.integrations.email import EmailConfig, EmailError

__all__ = ["EmailError", "EmailMixin", "EmailStatus"]


@dataclass
class EmailStatus:
    connected: bool
    host: str
    port: int
    username: str
    sender: str
    allowed_recipients: list[str]


class EmailMixin(ServiceBase):
    async def email_status(self) -> EmailStatus:
        return _status(await email.load(self._storage.store))

    async def connect_email(self, host: str, port: int, username: str, password: str, sender: str) -> EmailStatus:
        """Check the login with the server, then save. Raises EmailError."""
        current = await email.load(self._storage.store)
        config = EmailConfig(host.strip(), port, username.strip(), password, sender.strip(), current.allowed_recipients)
        await email.verify(config)
        await email.save(self._storage.store, config)
        return _status(config)

    async def set_email_recipients(self, addresses: list[str]) -> EmailStatus:
        config = await email.load(self._storage.store)
        config.allowed_recipients = sorted({a.strip().lower() for a in addresses if a.strip()})
        await email.save(self._storage.store, config)
        return _status(config)

    async def disconnect_email(self) -> None:
        await email.clear(self._storage.store)


def _status(config: EmailConfig) -> EmailStatus:
    return EmailStatus(
        config.connected, config.host, config.port, config.username, config.sender, config.allowed_recipients
    )
