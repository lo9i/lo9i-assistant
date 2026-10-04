"""Addresses the agent may email without asking, from any account. The user's own accounts always
are. One list for the whole assistant, in the Store."""

from langgraph.store.base import BaseStore

from assistant.core import accounts
from assistant.core.integrations.email.accounts import KIND, list_accounts

_KEY = (("integrations",), "email_recipients")
# Where each account kept its own list before there was one for all.
_LEGACY_FIELD = "allowed_recipients"


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


async def migrate(store: BaseStore) -> None:
    """Joins the lists accounts kept before into the one list, and drops them from the accounts."""
    legacy = [a for a in await accounts.list_kind(store, KIND) if _LEGACY_FIELD in a.settings]
    if not legacy:
        return
    addresses = [x for a in legacy for x in a.settings[_LEGACY_FIELD]]
    await save(store, [*await get(store), *addresses])
    for account in legacy:
        del account.settings[_LEGACY_FIELD]
        await accounts.save(store, account)
