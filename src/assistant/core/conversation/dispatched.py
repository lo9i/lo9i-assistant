"""Messages the inbox sent on to a conversation (core/conversation/dispatch.py), and work the assistant
moved out of it (core/tools/side.py). What's kept is the message as the inbox got it, files and what a
voice note said included, so nothing is uploaded or transcribed again, and the conversation it was last
sent to: a message moved later (dispatch_nodes.py) is sent again by the same id, and the conversation it
left is told (moved.py). A coding task moved out of the inbox keeps the agent its new conversation is
handed to. One Store record per message under ("dispatched", user_id)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.store.base import BaseStore

# The key of the message's id in the response_metadata of the line the inbox records for it, which history
# shows with a way to move it.
DISPATCH_ID = "lo9i_dispatch_id"


@dataclass(frozen=True)
class Kept:
    id: str
    content: list[Any]
    # The message's text, without its turn header and notes.
    said: str
    # The conversation it was last sent to; "" until it's sent.
    sent_to: str
    # The coding agent its conversation is handed to before it's sent: command, folder and name.
    handoff: dict[str, str] | None = None
    # The quick exchange in the inbox it followed up, which its new conversation shows (carried.py).
    carried: list[dict[str, str]] = field(default_factory=list)


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("dispatched", user_id)


async def keep(
    store: BaseStore,
    user_id: str,
    content: list[Any],
    said: str,
    handoff: dict[str, str] | None = None,
    carried: list[dict[str, str]] | None = None,
) -> str:
    """Keeps the message's content blocks and returns the id it's sent with."""
    dispatch_id = uuid4().hex
    at = datetime.now(UTC).isoformat()
    value = {"content": content, "said": said, "sent_to": "", "at": at, "handoff": handoff, "carried": carried or []}
    await store.aput(_namespace(user_id), dispatch_id, value)
    return dispatch_id


async def load(store: BaseStore, user_id: str, dispatch_id: str) -> Kept | None:
    item = await store.aget(_namespace(user_id), dispatch_id)
    return None if item is None else _kept(item.key, item.value)


async def latest(store: BaseStore, user_id: str) -> Kept | None:
    """The message the inbox sent on last."""
    items = await store.asearch(_namespace(user_id), limit=10_000)
    item = max(items, key=lambda item: item.value.get("at", ""), default=None)
    return None if item is None else _kept(item.key, item.value)


async def places(store: BaseStore, user_id: str) -> dict[str, str]:
    """Each kept message's conversation ("" until it's sent), by its id."""
    return {item.key: item.value.get("sent_to", "") for item in await store.asearch(_namespace(user_id), limit=10_000)}


async def sent(store: BaseStore, user_id: str, kept: Kept, thread_id: str) -> None:
    """Records that the message is now in `thread_id`."""
    item = await store.aget(_namespace(user_id), kept.id)
    if item is not None:
        await store.aput(_namespace(user_id), kept.id, item.value | {"sent_to": thread_id})


def _kept(dispatch_id: str, value: dict[str, Any]) -> Kept:
    content, said, sent_to = list(value["content"]), value.get("said", ""), value.get("sent_to", "")
    return Kept(dispatch_id, content, said, sent_to, value.get("handoff"), list(value.get("carried") or []))
