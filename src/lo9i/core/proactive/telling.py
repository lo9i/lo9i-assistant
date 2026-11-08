"""Telling the user something on the assistant's own initiative (the briefing, a reminder): into the notifications
feed when it needs the user (a reminder; core/notifications.py), and to the user's own chat on every chat channel
connected now, recorded for the turn header of their next message there (core/conversation/sent.py), so a reply
("done", "less of this") arrives with what it answers. With no channel connected, a reminder is read in the feed."""

from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from lo9i.core import notifications
from lo9i.core.conversation import sent
from lo9i.core.notifications import Kind
from lo9i.core.outbox import Outbox


class Teller:
    def __init__(self, store: BaseStore, outbox: Outbox, user_id: str) -> None:
        self._store = store
        self._outbox = outbox
        self._user_id = user_id

    async def tell(self, kind: Kind, title: str, text: str, thread_id: str = "") -> list[str]:
        """The chat channels that took it. `thread_id`: the conversation it's about, which its notification opens."""
        await notifications.add(self._store, self._user_id, kind, title, text, ok=True, thread_id=thread_id)
        return await sent.tell_every_channel(
            self._store, self._outbox, self._user_id, text, datetime.now(UTC), proactive=True
        )
