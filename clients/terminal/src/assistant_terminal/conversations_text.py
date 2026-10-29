"""Conversations as text, shared by the /conversations screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Conversation, ShownMessage
from assistant.core.config import settings
from assistant_terminal.i18n import short_date, t

# Messages shown in a conversation's preview.
_PREVIEW = 6


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
