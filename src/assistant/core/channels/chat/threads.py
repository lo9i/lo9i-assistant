"""Which conversation each message in a channel's chat belongs to, so replying to one continues it, and a
channel's /clear, which sends its next message to a new conversation instead of the inbox. The messages are
kept per chat, the latest _KEPT, in one Store record under ("channel_messages", user_id, channel) keyed by
the chat's id; /clear under ("channel_new", user_id).

Messages the assistant starts (send_message, the end of background work) go to the user's own chat
(OWN_CHAT), whose real id the daemon doesn't know: they're kept under it, and a reply in any chat looks
there too. A message sent to several paired Telegram accounts is kept by its id in each of them, as the channel
lists them.

/clear names the new conversation at once, so what's done before the next message (pinning a skill) goes to it."""

from langgraph.store.base import BaseStore

from assistant.core.channels.chat.port import OWN_CHAT

_KEPT = 500


def _messages(user_id: str, channel: str) -> tuple[str, ...]:
    return ("channel_messages", user_id, channel)


def _new(user_id: str) -> tuple[str, ...]:
    return ("channel_new", user_id)


async def record(store: BaseStore, user_id: str, channel: str, chat: str, messages: list[str], thread_id: str) -> None:
    """The chat's `messages` (their ids in the channel) belong to `thread_id`."""
    item = await store.aget(_messages(user_id, channel), chat)
    kept: dict[str, str] = dict(item.value["messages"]) if item else {}
    for message in messages:
        kept.pop(message, None)
        kept[message] = thread_id
    latest = dict(list(kept.items())[-_KEPT:])
    await store.aput(_messages(user_id, channel), chat, {"messages": latest})


async def thread_of(store: BaseStore, user_id: str, channel: str, chat: str, message: str) -> str | None:
    """The conversation the chat's message belongs to, kept in that chat or in the user's own; None for one
    not kept."""
    for kept_in in dict.fromkeys([chat, OWN_CHAT]):
        item = await store.aget(_messages(user_id, channel), kept_in)
        if item is not None and (thread_id := item.value["messages"].get(message)):
            return thread_id
    return None


async def record_own(store: BaseStore, user_id: str, channel: str, messages: list[str], thread_id: str) -> None:
    """Messages the assistant started in the user's own chat on the channel belong to `thread_id`."""
    await record(store, user_id, channel, OWN_CHAT, messages, thread_id)


async def want_new(store: BaseStore, user_id: str, channel: str, thread_id: str) -> None:
    """The channel's next message goes to `thread_id`, a new conversation."""
    await store.aput(_new(user_id), channel, {"thread_id": thread_id})


async def new_waiting(store: BaseStore, user_id: str, channel: str) -> str | None:
    """The new conversation the channel's /clear waits to send its next message to; None when none waits, "" for a
    /clear from before they were named."""
    item = await store.aget(_new(user_id), channel)
    return None if item is None else str(item.value.get("thread_id", ""))


async def forget_new(store: BaseStore, user_id: str, channel: str) -> None:
    await store.adelete(_new(user_id), channel)


async def forget(store: BaseStore, user_id: str, channels: list[str], thread_id: str) -> None:
    """For a deleted conversation: replying to its messages goes to the inbox."""
    for channel in channels:
        for item in await store.asearch(_messages(user_id, channel), limit=1000):
            kept = {m: t for m, t in item.value["messages"].items() if t != thread_id}
            if len(kept) != len(item.value["messages"]):
                await store.aput(_messages(user_id, channel), item.key, {"messages": kept})
