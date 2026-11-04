"""The inbox: where a message goes when it isn't written in a conversation, one per user. It doesn't keep
topics: each message is routed (core/conversation/dispatch_nodes.py) to the conversation it continues or a
new one, and only a quick question is answered here. Memory is shared by every conversation.

A chat channel (Telegram, Slack) writes every new message to the inbox; the conversation its last message
went to is kept under ("threads", user_id), by channel's name.

Before the inbox, one home conversation answered everything; `legacy_home` finds it so it's kept as an
archived conversation (core/agent/threads.py::retire_home)."""

from langgraph.store.base import BaseStore

_KEY = "thread_id"


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("inbox", user_id)


def _home_namespace(user_id: str) -> tuple[str, ...]:
    return ("home", user_id)


async def current(store: BaseStore, user_id: str) -> str | None:
    """The inbox's thread id, or None before it's started."""
    item = await store.aget(_namespace(user_id), _KEY)
    return item.value["thread_id"] if item else None


async def start(store: BaseStore, user_id: str, thread_id: str) -> None:
    await store.aput(_namespace(user_id), _KEY, {"thread_id": thread_id})


def channels_namespace(user_id: str) -> tuple[str, ...]:
    """Where the conversation each chat channel last wrote in is kept, under the channel's name."""
    return ("threads", user_id)


async def channel_thread(store: BaseStore, user_id: str, channel: str) -> str | None:
    """The conversation the channel's last message went to, or the inbox (None before it's started)."""
    item = await store.aget(channels_namespace(user_id), channel)
    return item.value["thread_id"] if item else await current(store, user_id)


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: if it was the inbox, the next use starts a new one."""
    if await current(store, user_id) == thread_id:
        await store.adelete(_namespace(user_id), _KEY)


async def legacy_home(store: BaseStore, user_id: str) -> str | None:
    """The home conversation from before the inbox, until it's retired."""
    item = await store.aget(_home_namespace(user_id), _KEY)
    return item.value["thread_id"] if item else None


async def drop_legacy_home(store: BaseStore, user_id: str) -> None:
    await store.adelete(_home_namespace(user_id), _KEY)
