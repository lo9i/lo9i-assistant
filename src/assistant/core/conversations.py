"""An index of the user's conversations, for listing and resuming them. One Store record per
conversation, under ("conversations", user_id). Scheduled job runs aren't listed."""

from dataclasses import asdict, dataclass, field

from langgraph.store.base import BaseStore

_SCAN_LIMIT = 1000
_TITLE_CHARS = 80


@dataclass
class Conversation:
    thread_id: str
    title: str
    started_at: str
    updated_at: str
    # Messages already summarized into memory, so leaving the conversation again only
    # summarizes what came after.
    archived_upto: int = 0
    # Whether the title was written by the model, rather than taken from the first message.
    titled: bool = False
    # The channels its messages came from (cli, web, telegram), in the order they were first used.
    channels: list[str] = field(default_factory=list)
    # What it's about (names, topics), written by the model with the title; a message in the inbox is
    # matched against them (core/conversation/related.py).
    tags: list[str] = field(default_factory=list)
    # Kept to read, never routed to: the home conversation from before the inbox (core/inbox.py).
    archived: bool = False
    # Whether it's the inbox (core/inbox.py). Set when listed, not stored.
    inbox: bool = False


def namespace(user_id: str) -> tuple[str, ...]:
    return ("conversations", user_id)


def title_from(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= _TITLE_CHARS else line[: _TITLE_CHARS - 1] + "…"


async def load(store: BaseStore, user_id: str, thread_id: str) -> Conversation | None:
    item = await store.aget(namespace(user_id), thread_id)
    return Conversation(**item.value) if item else None


async def save(store: BaseStore, user_id: str, conversation: Conversation) -> None:
    record = {k: v for k, v in asdict(conversation).items() if k != "inbox"}
    await store.aput(namespace(user_id), conversation.thread_id, record)


async def recent(store: BaseStore, user_id: str) -> list[Conversation]:
    """Newest activity first."""
    items = await store.asearch(namespace(user_id), limit=_SCAN_LIMIT)
    return sorted((Conversation(**i.value) for i in items), key=lambda c: c.updated_at, reverse=True)


async def set_title(store: BaseStore, user_id: str, thread_id: str, title: str, tags: list[str]) -> bool:
    """False for an empty title, an unknown conversation or an archived one, which keeps its own."""
    conversation = await load(store, user_id, thread_id)
    if conversation is None or not title or conversation.archived:
        return False
    conversation.title, conversation.titled, conversation.tags = title_from(title), True, tags
    await save(store, user_id, conversation)
    return True


async def remove(store: BaseStore, user_id: str, thread_id: str) -> None:
    await store.adelete(namespace(user_id), thread_id)


async def mark_archived(store: BaseStore, user_id: str, thread_id: str, upto: int) -> None:
    """Messages before `upto` are summarized into memory. Nothing to mark for an unlisted conversation."""
    conversation = await load(store, user_id, thread_id)
    if conversation is not None:
        conversation.archived_upto = upto
        await save(store, user_id, conversation)


async def set_channels(store: BaseStore, user_id: str, thread_id: str, channels: list[str]) -> None:
    conversation = await load(store, user_id, thread_id)
    if conversation is not None:
        conversation.channels = channels
        await save(store, user_id, conversation)


async def archive(store: BaseStore, user_id: str, thread_id: str, title: str) -> None:
    """Keeps the conversation to read under `title`, out of routing. Nothing to do for an unlisted one."""
    conversation = await load(store, user_id, thread_id)
    if conversation is not None:
        conversation.title, conversation.titled, conversation.archived = title, True, True
        await save(store, user_id, conversation)


async def touch(store: BaseStore, user_id: str, thread_id: str, text: str, channel: str, now: str) -> None:
    """Record activity. A new conversation is titled after its first message."""
    conversation = await load(store, user_id, thread_id) or Conversation(thread_id, title_from(text), now, now)
    conversation.title = conversation.title or title_from(text)
    conversation.updated_at = now
    if channel not in conversation.channels:
        conversation.channels.append(channel)
    await save(store, user_id, conversation)
