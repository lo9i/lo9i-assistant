"""Reading a whole Store namespace, page by page."""

from langgraph.store.base import BaseStore, Item

_PAGE = 1000


async def all_items(store: BaseStore, namespace: tuple[str, ...]) -> list[Item]:
    items: list[Item] = []
    while page := await store.asearch(namespace, limit=_PAGE, offset=len(items)):
        items += page
        if len(page) < _PAGE:
            break
    return items
