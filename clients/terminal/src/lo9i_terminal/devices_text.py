"""Paired devices and pairing codes as text, for the /devices screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lo9i.core.agent import Device, PairingCode, Passkey
from lo9i.core.config import settings
from lo9i_terminal.i18n import short_date, t


def describe(device: Device, passkeys: list[Passkey]) -> str:
    """Markdown: the device, when it was paired and last used, and from where, and its passkeys."""
    used = t(
        "Last used {when} from {address}",
        when=_local(device.last_used_at),
        address=device.last_ip or t("an unknown address"),
    )
    paired = t("Paired {when}", when=_local(device.created_at))
    return f"### {device.name}\n\n{used}\n\n{paired}\n\n{_passkeys(passkeys)}"


def _passkeys(passkeys: list[Passkey]) -> str:
    if not passkeys:
        return t(
            "No passkeys. One is added in that browser, on the web app's Devices page, to sign in there without a code."
        )
    lines = [f"**{t('Passkeys')}**", ""]
    for passkey in passkeys:
        line = t("Added {added}, used {used}", added=_local(passkey.created_at), used=_local(passkey.last_used_at))
        lines.append(f"- {line}" + (f" ({t('synced')})" if passkey.synced else ""))
    return "\n".join(lines)


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
