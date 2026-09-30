"""Email settings (SMTP), stored as one Store record, and sending.

Connected from the app (/email): the password lives in the database, not in .env.
"""

from dataclasses import asdict, dataclass, field
from email.message import EmailMessage

import aiosmtplib
from langgraph.store.base import BaseStore

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

    @property
    def connected(self) -> bool:
        return bool(self.host and self.sender)

    def allowed(self, address: str) -> bool:
        return address.strip().lower() in {a.lower() for a in [self.sender, *self.allowed_recipients]}


async def load(store: BaseStore) -> EmailConfig:
    item = await store.aget(_NAMESPACE, _KEY)
    return EmailConfig(**item.value) if item else EmailConfig()


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
    # Port 465 uses TLS from the start; other ports (587) upgrade with STARTTLS.
    tls = config.port == 465
    return {"hostname": config.host, "port": config.port, "use_tls": tls, "start_tls": not tls, "timeout": _TIMEOUT}
