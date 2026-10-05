"""The home conversation: the one long-running conversation per user that chat channels write to
and the apps open on. Focused work goes to side conversations, which the user starts (/new) or the
agent suggests (core/tools/side.py); memory is shared by all of them. A chat channel on a side
conversation keeps it under ("threads", user_id) until its /home."""

from langgraph.store.base import BaseStore

_KEY = "thread_id"


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("home", user_id)


async def current(store: BaseStore, user_id: str) -> str | None:
    """The home conversation's thread id, or None before it's started."""
    item = await store.aget(_namespace(user_id), _KEY)
    return item.value["thread_id"] if item else None


async def start(store: BaseStore, user_id: str, thread_id: str) -> None:
    await store.aput(_namespace(user_id), _KEY, {"thread_id": thread_id})


def channels_namespace(user_id: str) -> tuple[str, ...]:
    """Where each chat channel's side conversation is kept, under the channel's name."""
    return ("threads", user_id)


async def channel_thread(store: BaseStore, user_id: str, channel: str) -> str | None:
    """The conversation the channel is on: its side conversation, or home (None before it's started)."""
    item = await store.aget(channels_namespace(user_id), channel)
    return item.value["thread_id"] if item else await current(store, user_id)


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: if it was home, the next use starts a new one."""
    if await current(store, user_id) == thread_id:
        await store.adelete(_namespace(user_id), _KEY)
