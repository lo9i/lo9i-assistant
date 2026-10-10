"""Messages waiting to be sent in a conversation once its current run ends: a coding task the assistant
handed to its agent along with the side conversation it's in (core/agent_tasks/tools.py). The daemon sends
each as a run of its own, so every app shows the agent's work in that conversation (daemon/queued.py).
Kept in the Store, so a restart doesn't lose one."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore


@dataclass(frozen=True)
class Queued:
    # The channel the conversation was on when it was queued: the run is sent from it.
    channel: str
    text: str


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("queued_messages", user_id)


async def add(store: BaseStore, user_id: str, thread_id: str, queued: Queued) -> None:
    item = await store.aget(_namespace(user_id), thread_id)
    waiting = [*(item.value["messages"] if item else []), {"channel": queued.channel, "text": queued.text}]
    await store.aput(_namespace(user_id), thread_id, {"messages": waiting})


async def take(store: BaseStore, user_id: str, thread_id: str) -> Queued | None:
    """The oldest message waiting in the conversation, which is no longer kept."""
    item = await store.aget(_namespace(user_id), thread_id)
    if item is None:
        return None
    first, *rest = item.value["messages"]
    if rest:
        await store.aput(_namespace(user_id), thread_id, {"messages": rest})
    else:
        await store.adelete(_namespace(user_id), thread_id)
    return Queued(first["channel"], first["text"])


async def threads(store: BaseStore, user_id: str) -> list[str]:
    """The conversations with messages waiting."""
    return [item.key for item in await store.asearch(_namespace(user_id), limit=1000)]
