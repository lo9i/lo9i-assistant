"""Telling the user something on the assistant's own initiative (the briefing, a reminder): into the notifications
feed, which the apps show and keep, and to the user's own chat on every chat channel connected now, recorded for the
turn header of their next message there (core/conversation/sent.py), so a reply ("done", "less of this") arrives
with what it answers. With no channel connected, the feed is where it's read."""

from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from assistant.core import notifications
from assistant.core.conversation import sent
from assistant.core.notifications import Kind
from assistant.core.outbox import Outbox


class Teller:
    def __init__(self, store: BaseStore, outbox: Outbox, user_id: str) -> None:
        self._store = store
        self._outbox = outbox
        self._user_id = user_id

    async def tell(self, kind: Kind, title: str, text: str, thread_id: str = "") -> list[str]:
        """The chat channels that took it. `thread_id`: the conversation it's about, which its notification opens."""
        await notifications.add(self._store, self._user_id, kind, title, text, ok=True, thread_id=thread_id)
        return await sent.tell_every_channel(self._store, self._outbox, self._user_id, text, datetime.now(UTC))
