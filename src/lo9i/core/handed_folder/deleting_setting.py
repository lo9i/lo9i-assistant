"""Whether the folder panel may delete files (deleting.py): off until the user turns it on in Settings → General, since
a paired device could otherwise delete any file the panel shows, the home folder's included. One Store record."""

from langgraph.store.base import BaseStore

_NAMESPACE = ("settings",)
_KEY = "folder_deleting"


async def allowed(store: BaseStore) -> bool:
    item = await store.aget(_NAMESPACE, _KEY)
    return bool(item and item.value.get("enabled"))


async def allow(store: BaseStore, enabled: bool) -> None:
    await store.aput(_NAMESPACE, _KEY, {"enabled": enabled})
