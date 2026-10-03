"""Sending mail over SMTP with an email account's settings."""

from email.message import EmailMessage

import aiosmtplib
import certifi

from assistant.core.integrations.email.accounts import EmailConfig, EmailError

_TIMEOUT = 20


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
