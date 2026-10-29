"""Paired devices and pairing codes as text, for the /devices screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Device, PairingCode
from assistant.core.config import settings
from assistant_terminal.i18n import short_date, t


def describe(device: Device) -> str:
    """Markdown: the device, when it was paired and last used, and from where."""
    used = t(
        "Last used {when} from {address}",
        when=_local(device.last_used_at),
        address=device.last_ip or t("an unknown address"),
    )
    return f"### {device.name}\n\n{used}\n\n" + t("Paired {when}", when=_local(device.created_at))


def pairing(code: PairingCode) -> str:
    """Markdown: what to do with a new code on the other device."""
    where = f"https://{settings.https_host}/app/" if settings.https_host else t("the assistant's web address")
    return (
        f"### {t('Pair a browser')}\n\n"
        f"{t('On the other device, open {where} and enter this code:', where=where)}\n\n"
        f"**{code.code}**\n\n"
        f"{t('It works once, until {until}.', until=_local(code.expires_at))}"
    )


def _local(timestamp: str) -> str:
    return short_date(datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)))
