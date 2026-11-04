"""Conversations as text, shared by the /conversations screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Conversation, ShownMessage
from assistant.core.config import settings
from assistant_terminal.i18n import short_date, t

# Messages shown in a conversation's preview.
_PREVIEW = 6

# The shortest search the daemon looks for in messages, as the web app's: one letter starts most of their words.
_MESSAGE_SEARCH_MIN = 2


def listed_title(conversation: Conversation) -> str:
    """The inbox by its name, an archived conversation marked."""
    if conversation.inbox:
        return t("Inbox (quick questions)")
    return t("{title} (archived)", title=conversation.title) if conversation.archived else conversation.title


def when(conversation: Conversation) -> str:
    return short_date(datetime.fromisoformat(conversation.updated_at).astimezone(ZoneInfo(settings.timezone)))


def preview(conversation: Conversation, messages: list[ShownMessage]) -> str:
    """Markdown: the title, its tags, and the last few things said."""
    said = [m for m in messages if m.role in ("user", "assistant")][-_PREVIEW:]
    lines = [f"**{t('You') if m.role == 'user' else t('Assistant')}:** {m.text}" for m in said]
    tags = t("Tags: {tags}", tags=", ".join(conversation.tags)) + "\n\n" if conversation.tags else ""
    active = t("Last active {when}", when=when(conversation))
    return f"### {listed_title(conversation)}\n\n{active}\n\n{tags}" + "\n\n".join(lines)


def message_search(query: str) -> str:
    """What the daemon is asked to look for in messages for `query`; "" for nothing."""
    words = query.strip()
    return words if len(words) >= _MESSAGE_SEARCH_MIN else ""


def matching(conversations: list[Conversation], query: str, containing: set[str]) -> list[Conversation]:
    """Those whose title holds `query`, or whose messages the daemon found it in (`containing`, their ids)."""
    words = query.strip().lower()
    if not words:
        return list(conversations)
    found = containing if message_search(words) else set()
    return [c for c in conversations if words in listed_title(c).lower() or c.thread_id in found]
