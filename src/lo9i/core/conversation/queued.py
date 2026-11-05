"""Messages waiting to be sent in a conversation once its current run ends: a follow-up on background work that ended
there (core/background.py), which the assistant answers with no message from the user, and what the user sent the
agent the conversation is handed to that it hadn't taken when they stopped it (core/agent/handoffs.py). The daemon
sends each as a run of its own, so every app shows it in that conversation (daemon/queued.py). Kept in the Store, so a
restart doesn't lose one."""

from dataclasses import dataclass, field

from langgraph.store.base import BaseStore


@dataclass(frozen=True)
class Queued:
    # The channel the conversation was on when it was queued: the run is sent from it.
    channel: str
    # The message; for a follow-up, what ended, as the user was told.
    text: str
    follow_up: bool = False
    # A coding task, which the assistant wrote and not the user (core/conversation/briefs.py): its agent's name. Only
    # in messages an earlier lo9i queued, which handed a conversation to the agent with its task.
    brief: str = ""
    # The files sent with it, already saved under the uploads dir: their references (path, name, media_type).
    files: list[dict[str, str]] = field(default_factory=list)
    # Messages the agent the conversation is handed to hadn't taken, sent again (core/conversation/resent.py).
    resent: bool = False


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("queued_messages", user_id)


async def add(store: BaseStore, user_id: str, thread_id: str, queued: Queued) -> None:
    item = await store.aget(_namespace(user_id), thread_id)
    added = {
        "channel": queued.channel,
        "text": queued.text,
        "follow_up": queued.follow_up,
        "brief": queued.brief,
        "files": queued.files,
        "resent": queued.resent,
    }
    waiting = [*(item.value["messages"] if item else []), added]
    await store.aput(_namespace(user_id), thread_id, {"messages": waiting})


async def first(store: BaseStore, user_id: str, thread_id: str) -> Queued | None:
    """The oldest message waiting in the conversation, still kept."""
    item = await store.aget(_namespace(user_id), thread_id)
    return _queued(item.value["messages"][0]) if item else None


async def take(store: BaseStore, user_id: str, thread_id: str) -> Queued | None:
    """The oldest message waiting in the conversation, which is no longer kept."""
    item = await store.aget(_namespace(user_id), thread_id)
    if item is None:
        return None
    oldest, *rest = item.value["messages"]
    if rest:
        await store.aput(_namespace(user_id), thread_id, {"messages": rest})
    else:
        await store.adelete(_namespace(user_id), thread_id)
    return _queued(oldest)


def _queued(kept: dict) -> Queued:
    brief, files = str(kept.get("brief") or ""), list(kept.get("files") or [])
    follow_up, resent = bool(kept.get("follow_up")), bool(kept.get("resent"))
    return Queued(kept["channel"], kept["text"], follow_up, brief, files, resent)


async def threads(store: BaseStore, user_id: str) -> list[str]:
    """The conversations with messages waiting."""
    return [item.key for item in await store.asearch(_namespace(user_id), limit=1000)]


async def waiting(store: BaseStore, user_id: str) -> dict[str, list[Queued]]:
    """Every conversation's messages waiting, oldest first, without taking them."""
    found = await store.asearch(_namespace(user_id), limit=1000)
    return {item.key: [_queued(kept) for kept in item.value["messages"]] for item in found}


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: nothing waits to be sent there any more."""
    await store.adelete(_namespace(user_id), thread_id)
