"""Paired devices and pairing codes as text, for the /devices screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Device, PairingCode
from assistant.core.config import settings


def describe(device: Device) -> str:
    """Markdown: the device, when it was paired and last used, and from where."""
    return (
        f"### {device.name}\n\n"
        f"Last used {_local(device.last_used_at)} from {device.last_ip or 'an unknown address'}\n\n"
        f"Paired {_local(device.created_at)}"
    )


def pairing(code: PairingCode) -> str:
    """Markdown: what to do with a new code on the other device."""
    where = f"https://{settings.https_host}/app/" if settings.https_host else "the assistant's web address"
    return (
        f"### Pair a browser\n\n"
        f"On the other device, open {where} and enter this code:\n\n"
        f"**{code.code}**\n\n"
        f"It works once, until {_local(code.expires_at)}."
    )


def _local(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)).strftime("%a %d %b %H:%M")
