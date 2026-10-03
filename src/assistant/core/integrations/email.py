"""Email settings (SMTP for sending, IMAP for reading), stored as one Store record, and sending.

Connected from the app (/email): the password lives in the database, not in .env.
"""

from dataclasses import asdict, dataclass, field
from email.message import EmailMessage

import aiosmtplib
import certifi
from langgraph.store.base import BaseStore

from assistant.core.integrations.email_providers import imap_host_for

_NAMESPACE = ("integrations",)
_KEY = "email"
_TIMEOUT = 20


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

    @property
    def connected(self) -> bool:
        return bool(self.host and self.sender)

    @property
    def can_read(self) -> bool:
        return self.connected and bool(self.imap_host)

    def allowed(self, address: str) -> bool:
        return address.strip().lower() in {a.lower() for a in [self.sender, *self.allowed_recipients]}


async def load(store: BaseStore) -> EmailConfig:
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return EmailConfig()
    config = EmailConfig(**item.value)
    # Saved before reading mail existed: a provider's IMAP server is known from its SMTP server.
    if "imap_host" not in item.value:
        config.imap_host = imap_host_for(config.host)
    return config


async def save(store: BaseStore, config: EmailConfig) -> None:
    await store.aput(_NAMESPACE, _KEY, asdict(config))


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)


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
