"""Messages waiting to be sent in a conversation once its current run ends: a coding task the assistant
handed to its agent along with the conversation it's in (core/agent_tasks/tools.py), a follow-up on
background work that ended there (core/background.py), which the assistant answers with no message from the
user, and what the user sent the agent the conversation is handed to that it hadn't taken when they stopped it
(core/agent/handoffs.py). The daemon sends each as a run of its own, so every app shows it in that conversation
(daemon/queued.py). Kept in the Store, so a restart doesn't lose one.

A coding task goes only with its conversation handed to its agent (core/agent/tasks.py::next_queued): one kept for
after a pending restart carries the handoff (`hand_to`), made as it's sent, so the conversation is never handed over
without it; one whose conversation was taken back before it went is dropped, never sent to the assistant as if the
user had written it."""

from dataclasses import asdict, dataclass, field

from langgraph.store.base import BaseStore

from lo9i.core.conversation.handoffs import Handoff


@dataclass(frozen=True)
class Queued:
    # The channel the conversation was on when it was queued: the run is sent from it.
    channel: str
    # The message; for a follow-up, what ended, as the user was told.
    text: str
    follow_up: bool = False
    # A coding task, which the assistant wrote and not the user (core/conversation/briefs.py): its agent's name.
    brief: str = ""
    # The files sent with it, already saved under the uploads dir: their references (path, name, media_type).
    files: list[dict[str, str]] = field(default_factory=list)
    # Messages the agent the conversation is handed to hadn't taken, sent again (core/conversation/resent.py).
    resent: bool = False
    # For a coding task kept for after a restart: the conversation is handed to its agent as the task is sent.
    hand_to: Handoff | None = None


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
        "hand_to": asdict(queued.hand_to) if queued.hand_to else None,
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
    hand_to = Handoff(**kept["hand_to"]) if kept.get("hand_to") else None
    follow_up, resent = bool(kept.get("follow_up")), bool(kept.get("resent"))
    return Queued(kept["channel"], kept["text"], follow_up, brief, files, resent, hand_to)


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
