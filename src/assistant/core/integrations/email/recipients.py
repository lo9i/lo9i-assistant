"""Addresses the agent may email without asking, from any account. The user's own accounts always
are. One list for the whole assistant, in the Store."""

from langgraph.store.base import BaseStore

from assistant.core.integrations.email.accounts import list_accounts

_KEY = (("integrations",), "email_recipients")


async def get(store: BaseStore) -> list[str]:
    item = await store.aget(*_KEY)
    return list(item.value["addresses"]) if item else []


async def save(store: BaseStore, addresses: list[str]) -> list[str]:
    """Lowercased, sorted, without duplicates or blanks."""
    cleaned = sorted({a.strip().lower() for a in addresses if a.strip()})
    await store.aput(*_KEY, {"addresses": cleaned})
    return cleaned


async def allowed(store: BaseStore, address: str) -> bool:
    own = {c.sender.lower() for c in await list_accounts(store)}
    return address.strip().lower() in own | set(await get(store))
