"""The header at the start of every user message: date, time and channel, then the messages the
assistant sent on this channel from elsewhere since the user last wrote (core/conversation/sent.py),
and notes for the assistant (the offer to get to know the user, core/conversation/introduction.py)."""

import re
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core.config import settings

_HEADER = re.compile(r"^\[[^\]]*, via ([\w-]+)\]$")
_HEADER_TIME = re.compile(r"^\[\w+ (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) ")
_SENT = "[You sent this on "
_NOTE = "[Note for you, not from the user:]"


def header_block(channel: str, now: datetime) -> dict[str, str]:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return {"type": "text", "text": f"[{local:%a %Y-%m-%d %H:%M %Z}, via {channel}]"}


def sent_block(channel: str, at: datetime, text: str) -> dict[str, str]:
    local = at.astimezone(ZoneInfo(settings.timezone))
    return {"type": "text", "text": f"{_SENT}{channel} at {local:%a %Y-%m-%d %H:%M %Z}, outside this chat:]\n{text}"}


def note_block(text: str) -> dict[str, str]:
    return {"type": "text", "text": f"{_NOTE}\n{text}"}


def is_header(block: object) -> bool:
    """True for the blocks `header_block`, `sent_block` and `note_block` made, so displays can leave
    them out."""
    if _channel(block) is not None:
        return True
    return isinstance(block, dict) and str(block.get("text", "")).startswith((_SENT, _NOTE))


def said(message: BaseMessage) -> str:
    """The message's text, without its turn header and notes."""
    blocks = message.content if isinstance(message.content, list) else [{"type": "text", "text": message.content}]
    texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text" and not is_header(b)]
    return "\n".join(t for t in texts if t.strip())


def is_date_header(block: object) -> bool:
    """True for the block `header_block` made: the date, time and channel, without the notes after it."""
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


def sent_at(message: HumanMessage) -> str | None:
    """The local date and time in the message's turn header ("2026-09-30 14:05"), None without one."""
    first = message.content[0] if isinstance(message.content, list) and message.content else None
    if not isinstance(first, dict) or _channel(first) is None:
        return None
    match = _HEADER_TIME.match(str(first.get("text", "")))
    return match.group(1) if match else None


def _channel(block: object) -> str | None:
    if not (isinstance(block, dict) and block.get("type") == "text"):
        return None
    match = _HEADER.match(str(block.get("text", "")))
    return match.group(1) if match else None
