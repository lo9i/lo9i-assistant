"""Archived parts of conversations whose memory isn't digested yet, one Store record each under
("memory_pending", user_id). A new epoch or a conversation being left adds one; the memory writer
(memory_writer.py) digests it and removes it, so a part the daemon stopped before digesting is
digested on the next start.
"""

from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore

from assistant.core.memory.items import all_items


@dataclass
class PendingPart:
    thread_id: str
    # Messages [start, end) of the conversation's checkpoint.
    start: int
    end: int
    # The conversation's running summary before this part, as context for the digest.
    previous_summary: str
    started_at: str
    ended_at: str


def namespace(user_id: str) -> tuple[str, ...]:
    return ("memory_pending", user_id)


async def add(store: BaseStore, user_id: str, part: PendingPart) -> None:
    await store.aput(namespace(user_id), _key(part), asdict(part))


async def remove(store: BaseStore, user_id: str, part: PendingPart) -> None:
    await store.adelete(namespace(user_id), _key(part))


async def load_all(store: BaseStore, user_id: str) -> list[PendingPart]:
    """Oldest first, so memory is updated in the order the conversations went."""
    parts = [PendingPart(**i.value) for i in await all_items(store, namespace(user_id))]
    return sorted(parts, key=lambda p: (p.ended_at, p.start))


async def users(store: BaseStore) -> set[str]:
    listed = await store.alist_namespaces(prefix=("memory_pending",), max_depth=2)
    return {ns[1] for ns in listed if len(ns) == 2}


def _key(part: PendingPart) -> str:
    return f"{part.thread_id}:{part.start}"
