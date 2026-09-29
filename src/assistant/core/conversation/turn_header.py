"""The header at the start of every user message: date, time and channel."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.config import settings


def header_block(channel: str, now: datetime) -> dict[str, str]:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return {"type": "text", "text": f"[{local:%a %Y-%m-%d %H:%M %Z}, via {channel}]"}
