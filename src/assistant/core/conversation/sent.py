"""Messages the assistant sent on a channel from outside that channel's conversation: send_message
from a job or another chat, and new-mail alerts. They're kept until the user next writes on that
channel and then go into that message's turn header, so a reply to one arrives with its context.
"""

import uuid
from datetime import datetime

from langgraph.store.base import BaseStore

from assistant.core.conversation.turn_header import sent_block

_LIMIT = 20


def _namespace(user_id: str, channel: str) -> tuple[str, ...]:
    return ("sent_messages", user_id, channel)


async def record(store: BaseStore, user_id: str, channel: str, text: str, at: datetime) -> None:
    await store.aput(_namespace(user_id, channel), uuid.uuid4().hex, {"at": at.isoformat(), "text": text})


async def take(store: BaseStore, user_id: str, channel: str) -> list[dict[str, str]]:
    """The turn header blocks for the messages sent since the user last wrote here, oldest first.
    They're removed: each goes into one message only. Only the latest few are kept."""
    items = await store.asearch(_namespace(user_id, channel), limit=1000)
    for item in items:
        await store.adelete(_namespace(user_id, channel), item.key)
    notes = sorted((item.value for item in items), key=lambda v: v["at"])[-_LIMIT:]
    return [sent_block(channel, datetime.fromisoformat(n["at"]), n["text"]) for n in notes]
