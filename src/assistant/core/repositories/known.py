"""The repositories the Plugins page lists plugins from. Starts with the assistant's own extras;
the user adds and removes others."""

from langgraph.store.base import BaseStore

from assistant.core.repositories.checkout import check_url

EXTRAS = "https://github.com/lo9i/lo9i-assistant-extras"
_NAMESPACE = ("repositories",)
_KEY = "list"


async def load(store: BaseStore) -> list[str]:
    item = await store.aget(_NAMESPACE, _KEY)
    return list(item.value["urls"]) if item else [EXTRAS]


async def add(store: BaseStore, url: str) -> list[str]:
    """Raises RepositoryError for an address that isn't https."""
    url = url.strip().rstrip("/")
    check_url(url)
    urls = await load(store)
    if url not in urls:
        urls.append(url)
        await store.aput(_NAMESPACE, _KEY, {"urls": urls})
    return urls


async def remove(store: BaseStore, url: str) -> list[str]:
    urls = [u for u in await load(store) if u != url]
    await store.aput(_NAMESPACE, _KEY, {"urls": urls})
    return urls
