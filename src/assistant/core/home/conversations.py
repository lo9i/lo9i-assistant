"""Home's Conversations card, built by code (core/home/coded.py): the most recent conversations, each with when it
was last written in. The web app draws it live from the conversations
themselves; this result is what the other apps show (the terminal app's /home)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.config import settings
from assistant.core.conversations import Conversation
from assistant.core.home.model import HomeItem, SectionContent

# The conversations shown.
RECENT = 5


def shown(listed: list[Conversation]) -> list[Conversation]:
    """The most recent ones (`listed` is newest first), never the inbox nor an archived one."""
    return [c for c in listed if not c.inbox and not c.archived][:RECENT]


class ConversationsSection:
    def __init__(self, store: BaseStore, user_id: str, listed: Callable[[], Awaitable[list[Conversation]]]) -> None:
        """`listed` gives the user's conversations, newest activity first, the inbox marked."""
        self._store = store
        self._user_id = user_id
        self._listed = listed

    async def build(self) -> SectionContent:
        """In the language chosen when it's built."""
        t = await i18n.chosen(self._store)
        items = [_item(c, t("Untitled")) for c in shown(await self._listed())]
        return SectionContent(items=items, note="" if items else t("No conversations yet."))


def _item(conversation: Conversation, untitled: str) -> HomeItem:
    local = datetime.fromisoformat(conversation.updated_at).astimezone(ZoneInfo(settings.timezone))
    return HomeItem(title=conversation.title or untitled, date=local.date().isoformat(), time=local.strftime("%H:%M"))
