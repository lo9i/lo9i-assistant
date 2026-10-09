"""Conversations as text, shared by the /conversations screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Conversation, ShownMessage
from assistant.core.config import settings

# Messages shown in a conversation's preview.
_PREVIEW = 6


def when(conversation: Conversation) -> str:
    local = datetime.fromisoformat(conversation.updated_at).astimezone(ZoneInfo(settings.timezone))
    return local.strftime("%a %d %b %H:%M")


def preview(conversation: Conversation, messages: list[ShownMessage]) -> str:
    """Markdown: the title, its tags, and the last few things said."""
    said = [m for m in messages if m.role in ("user", "assistant")][-_PREVIEW:]
    lines = [f"**{'You' if m.role == 'user' else 'Assistant'}:** {m.text}" for m in said]
    tags = f"Tags: {', '.join(conversation.tags)}\n\n" if conversation.tags else ""
    return f"### {conversation.title}\n\nLast active {when(conversation)}\n\n{tags}" + "\n\n".join(lines)
