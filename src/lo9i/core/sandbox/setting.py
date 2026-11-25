"""Whether bash commands run in the sandbox: off until the user turns it on. One Store record."""

from langgraph.store.base import BaseStore

_NAMESPACE = ("settings",)
_KEY = "bash_sandbox"


async def enabled(store: BaseStore) -> bool:
    item = await store.aget(_NAMESPACE, _KEY)
    return bool(item and item.value.get("enabled"))


async def enable(store: BaseStore, on: bool) -> None:
    await store.aput(_NAMESPACE, _KEY, {"enabled": on})
