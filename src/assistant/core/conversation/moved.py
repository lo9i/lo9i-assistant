"""Messages the user moved out of a conversation they were sent on to (dispatched.py): history stays as
it was, so the conversation's next message says in its turn header which ones it should leave out, once.
One Store record per message under ("moved_away", user_id, thread_id)."""

from langgraph.store.base import BaseStore

from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block

# How much of each message the note quotes.
_QUOTED_CHARS = 200


def _namespace(user_id: str, thread_id: str) -> tuple[str, ...]:
    return ("moved_away", user_id, thread_id)


async def record(store: BaseStore, user_id: str, thread_id: str, dispatch_id: str, said: str) -> None:
    await store.aput(_namespace(user_id, thread_id), dispatch_id, {"said": said})


async def drop(store: BaseStore, user_id: str, thread_id: str, dispatch_id: str) -> None:
    """The message came back here."""
    await store.adelete(_namespace(user_id, thread_id), dispatch_id)


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    for item in await store.asearch(_namespace(user_id, thread_id), limit=1000):
        await store.adelete(_namespace(user_id, thread_id), item.key)


async def take(store: BaseStore, user_id: str, thread_id: str) -> list[dict[str, str]]:
    """The turn header note for the messages moved out since the user last wrote here, or nothing. The
    records are removed: each goes into one message only."""
    items = await store.asearch(_namespace(user_id, thread_id), limit=1000)
    if not items:
        return []
    await forget(store, user_id, thread_id)
    quoted = "\n".join(f"- “{_shortened(item.value['said'])}”" for item in items)
    return [note_block(prompts.load("moved_away").format(moved=quoted))]


def _shortened(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= _QUOTED_CHARS else line[: _QUOTED_CHARS - 1] + "…"
