"""The conversations the user pinned to Home, which its Conversations card shows in the order they were pinned: one
Store record under ("home", user_id), so every device shows the same ones. Writing it publishes a `home` event
(core/storage.py)."""

from langgraph.store.base import BaseStore

from assistant.core.home.sections import namespace

_KEY = "pinned"


async def load(store: BaseStore, user_id: str) -> list[str]:
    """Their ids, the first pinned first."""
    item = await store.aget(namespace(user_id), _KEY)
    return list(item.value["threads"]) if item else []


async def pin(store: BaseStore, user_id: str, thread_id: str) -> list[str]:
    """At the end, once."""
    pinned = await load(store, user_id)
    if thread_id not in pinned:
        pinned.append(thread_id)
        await _save(store, user_id, pinned)
    return pinned


async def unpin(store: BaseStore, user_id: str, thread_id: str) -> list[str]:
    pinned = await load(store, user_id)
    if thread_id in pinned:
        pinned.remove(thread_id)
        await _save(store, user_id, pinned)
    return pinned


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """When the conversation is deleted."""
    await unpin(store, user_id, thread_id)


async def _save(store: BaseStore, user_id: str, pinned: list[str]) -> None:
    await store.aput(namespace(user_id), _KEY, {"threads": pinned})
