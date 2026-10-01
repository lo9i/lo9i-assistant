"""The header at the start of every user message: date, time and channel."""

import re
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core.config import settings

_HEADER = re.compile(r"^\[[^\]]*, via ([\w-]+)\]$")


def header_block(channel: str, now: datetime) -> dict[str, str]:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return {"type": "text", "text": f"[{local:%a %Y-%m-%d %H:%M %Z}, via {channel}]"}


def is_header(block: object) -> bool:
    """True for the block `header_block` made, so displays can leave it out."""
    return _channel(block) is not None


def channels(messages: Sequence[BaseMessage]) -> list[str]:
    """The channels the user's messages came from, in the order they were first used."""
    found: dict[str, None] = {}
    for message in messages:
        if isinstance(message, HumanMessage) and isinstance(message.content, list) and message.content:
            channel = _channel(message.content[0])
            if channel is not None:
                found[channel] = None
    return list(found)


def _channel(block: object) -> str | None:
    if not (isinstance(block, dict) and block.get("type") == "text"):
        return None
    match = _HEADER.match(str(block.get("text", "")))
    return match.group(1) if match else None
