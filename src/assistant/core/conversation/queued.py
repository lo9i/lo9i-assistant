"""Messages waiting to be sent in a conversation once its current run ends: a coding task the assistant
handed to its agent along with the conversation it's in (core/agent_tasks/tools.py), and a follow-up on
background work that ended there (core/background.py), which the assistant answers with no message from the
user. The daemon sends each as a run of its own, so every app shows it in that conversation
(daemon/queued.py). Kept in the Store, so a restart doesn't lose one."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore


@dataclass(frozen=True)
class Queued:
    # The channel the conversation was on when it was queued: the run is sent from it.
    channel: str
    # The message; for a follow-up, what ended, as the user was told.
    text: str
    follow_up: bool = False
    # A coding task, which the assistant wrote and not the user (core/conversation/briefs.py): its agent's name.
    brief: str = ""


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("queued_messages", user_id)


async def add(store: BaseStore, user_id: str, thread_id: str, queued: Queued) -> None:
    item = await store.aget(_namespace(user_id), thread_id)
    added = {"channel": queued.channel, "text": queued.text, "follow_up": queued.follow_up, "brief": queued.brief}
    waiting = [*(item.value["messages"] if item else []), added]
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
    return Queued(first["channel"], first["text"], bool(first.get("follow_up")), str(first.get("brief") or ""))


async def threads(store: BaseStore, user_id: str) -> list[str]:
    """The conversations with messages waiting."""
    return [item.key for item in await store.asearch(_namespace(user_id), limit=1000)]
