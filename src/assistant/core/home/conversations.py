"""Home's Conversations card, built by code (core/home/coded.py): the conversations pinned to Home, or the most
recent ones while none is, each with when it was last written in. The web app draws it live from the conversations
themselves; this result is what the other apps show (the terminal app's /home)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.config import settings
from assistant.core.conversations import Conversation
from assistant.core.home import pins
from assistant.core.home.model import HomeItem, SectionContent

# The conversations shown while none is pinned.
RECENT = 5


def shown(listed: list[Conversation], pinned: list[str]) -> tuple[list[Conversation], bool]:
    """The pinned conversations still listed, in the order pinned, and True; or, with none, the most recent ones
    (`listed` is newest first) and False. Never the inbox, nor an archived one among the recent."""
    by_id = {c.thread_id: c for c in listed if not c.inbox}
    found = [by_id[t] for t in pinned if t in by_id]
    if found:
        return found, True
    return [c for c in by_id.values() if not c.archived][:RECENT], False


class ConversationsSection:
    def __init__(self, store: BaseStore, user_id: str, listed: Callable[[], Awaitable[list[Conversation]]]) -> None:
        """`listed` gives the user's conversations, newest activity first, the inbox marked."""
        self._store = store
        self._user_id = user_id
        self._listed = listed

    async def build(self) -> SectionContent:
        """In the language chosen when it's built."""
        t = await i18n.chosen(self._store)
        found, pinned = shown(await self._listed(), await pins.load(self._store, self._user_id))
        items = [_item(c, t("Untitled")) for c in found]
        if not items:
            return SectionContent(items=[], note=t("No conversations yet."))
        return SectionContent(
            items=items, note="" if pinned else t("Recent: pin a conversation to Home to keep it here.")
        )


def _item(conversation: Conversation, untitled: str) -> HomeItem:
    local = datetime.fromisoformat(conversation.updated_at).astimezone(ZoneInfo(settings.timezone))
    return HomeItem(title=conversation.title or untitled, date=local.date().isoformat(), time=local.strftime("%H:%M"))
