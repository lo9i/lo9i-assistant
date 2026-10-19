"""A message written in the inbox that obviously follows up the one before it goes where that one went,
without asking the worker model (dispatch_nodes.py), which otherwise costs a call before every message.

Obvious: the message before it was sent on to a conversation (not answered in the inbox), it came from the
same channel, that conversation was last written in under FOLLOW_UP_SECONDS ago, the message is short, and
none of its words match another conversation's tags (related.py), so it brings up no new topic. "and on
Saturday?" a minute after "book a table for Friday" on Telegram. A longer message, or one about something a
conversation's tags name, still goes to the model."""

from collections.abc import Sequence
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from assistant.core import conversations
from assistant.core.conversation import dispatched, related
from assistant.core.conversation.dispatch import Candidate
from assistant.core.conversation.dispatched import DISPATCH_ID
from assistant.core.conversation.turn_header import channels, said

FOLLOW_UP_SECONDS = 180
_MAX_WORDS = 12


async def last_place(store: BaseStore, user_id: str, messages: Sequence[BaseMessage]) -> str:
    """Where the inbox sent the message before the last one, where it is now (moves included); "" when the
    inbox answered it, or there was none."""
    line = next((m for m in reversed(messages[:-1]) if isinstance(m, AIMessage)), None)
    dispatch_id = line.response_metadata.get(DISPATCH_ID, "") if line is not None else ""
    kept = await dispatched.load(store, user_id, dispatch_id) if dispatch_id else None
    return kept.sent_to if kept is not None else ""


async def obvious(store: BaseStore, user_id: str, messages: Sequence[BaseMessage], found: Sequence[Candidate]) -> str:
    """The conversation the last message obviously follows up; "" when the model should pick."""
    place = await last_place(store, user_id, messages)
    message = messages[-1]
    if not place or not _same_channel(messages) or len(said(message).split()) > _MAX_WORDS:
        return ""
    conversation = await conversations.load(store, user_id, place)
    if conversation is None or conversation.archived or not _lately(conversation.updated_at):
        return ""
    matched = related.matches(said(message), {c.thread_id: c.tags for c in found})
    return place if not matched or matched[0] == place else ""


def _same_channel(messages: Sequence[BaseMessage]) -> bool:
    """The last two messages the user wrote came from the same channel."""
    written = [m for m in messages if isinstance(m, HumanMessage)][-2:]
    return len(written) == 2 and channels(written[:1]) == channels(written[1:])


def _lately(updated_at: str) -> bool:
    if not updated_at:
        return False
    at = datetime.fromisoformat(updated_at)
    at = at if at.tzinfo else at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - at).total_seconds() <= FOLLOW_UP_SECONDS
