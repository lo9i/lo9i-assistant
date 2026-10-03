"""The Brave Search API key, set by the user in the app and kept encrypted (core/secret_store.py)."""

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.internet.providers import BraveProvider, SearchError
from assistant.core.secret_store import SecretBox

_REF = "web_search_brave"


class InvalidSearchKeyError(Exception):
    """Brave didn't answer a search with the key."""


async def check(key: str) -> None:
    """One search with the key. Raises InvalidSearchKeyError."""
    try:
        await BraveProvider(key).search("weather", 1)
    except SearchError as e:
        raise InvalidSearchKeyError(f"Brave didn't accept the key: {e}") from e


async def save(store: BaseStore, box: SecretBox, key: str) -> None:
    await secret_store.put(store, box, _REF, key)


async def load(store: BaseStore, box: SecretBox) -> str:
    """The key, or "" when none is set. Raises SecretError when it can't be read."""
    return await secret_store.get(store, box, _REF)


async def clear(store: BaseStore) -> None:
    await secret_store.delete(store, _REF)
