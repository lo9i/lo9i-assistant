"""Each conversation's latest running summary (summary.py), kept apart from its checkpoint so routing reads
every conversation's without loading their messages: closeness in meaning embeds it (meanings.py), so a
conversation that moved on from what it began with is found by what it's about now. Saved when an epoch
starts with a new summary; one Store record per listed conversation under ("conversation_summaries",
user_id), a conversation never summarized having an empty one once the daemon caught up with it."""

from langgraph.store.base import BaseStore

from assistant.core import conversations


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("conversation_summaries", user_id)


async def save(store: BaseStore, user_id: str, thread_id: str, summary: str) -> None:
    """Only for a listed conversation: a scheduled job's runs aren't routed to."""
    if await conversations.load(store, user_id, thread_id) is not None:
        await store.aput(_namespace(user_id), thread_id, {"summary": summary})


async def of_user(store: BaseStore, user_id: str) -> dict[str, str]:
    """The summaries kept, by conversation; one never summarized has "" once the daemon caught up with it."""
    items = await store.asearch(_namespace(user_id), limit=100_000)
    return {item.key: str(item.value.get("summary", "")) for item in items}


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)
