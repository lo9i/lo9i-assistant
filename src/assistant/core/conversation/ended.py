"""Background work started in a conversation that ended (core/background.py): a note per piece of work,
kept until the user next writes in that conversation and then put into that message's turn header,
once. The assistant reading the end itself (task_status) drops its note: it already knows."""

from datetime import UTC, datetime

from langchain_core.messages import BaseMessage
from langgraph.store.base import BaseStore

from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block

# The key, in the additional_kwargs of the message a follow-up runs with (core/agent/messaging.py), of what
# ended as the user was told it; that message has no text of the user's.
FOLLOW_UP = "lo9i_follow_up"


def follow_up_notice(message: BaseMessage) -> str:
    """What ended, for a message a follow-up runs with; "" for any other."""
    notice = message.additional_kwargs.get(FOLLOW_UP)
    return notice if isinstance(notice, str) else ""


def _namespace(user_id: str, thread_id: str) -> tuple[str, ...]:
    return ("background_ended", user_id, thread_id)


async def record(store: BaseStore, user_id: str, thread_id: str, key: str, note: str) -> None:
    value = {"at": datetime.now(UTC).isoformat(), "note": note}
    await store.aput(_namespace(user_id, thread_id), key, value)


async def drop(store: BaseStore, user_id: str, thread_id: str, key: str) -> None:
    await store.adelete(_namespace(user_id, thread_id), key)


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    for item in await store.asearch(_namespace(user_id, thread_id), limit=1000):
        await store.adelete(_namespace(user_id, thread_id), item.key)


async def take(
    store: BaseStore, user_id: str, thread_id: str, prompt: str = "background_ended"
) -> list[dict[str, str]]:
    """The turn header note for the work that ended since the user last wrote here, oldest first, or
    nothing. The notes are removed: each goes into one message only. `prompt` words the note: the inbox's
    work is told in the conversation the inbox sent a message on to (`background_ended_in_inbox`)."""
    items = await store.asearch(_namespace(user_id, thread_id), limit=1000)
    if not items:
        return []
    await forget(store, user_id, thread_id)
    notes = [item.value["note"] for item in sorted(items, key=lambda item: item.value["at"])]
    return [note_block(prompts.load(prompt).format(ended="\n".join(f"- {n}" for n in notes)))]
