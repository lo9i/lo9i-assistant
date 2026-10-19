"""How sure the worker model has to be that a message in the inbox continues a conversation (or is a quick
question the inbox answers) for it to go there; below it, the message starts a new conversation, which a
wrong guess costs least (core/conversation/dispatch_nodes.py). Set in Settings → Model (/model), one Store
record; 0.7 until the user changes it."""

from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore

_NAMESPACE = ("settings",)
_KEY = "dispatch"


@dataclass(frozen=True)
class DispatchSetting:
    # From 0 to 1.
    confidence: float = 0.7


DEFAULT = DispatchSetting()


class DispatchSettingError(ValueError):
    """A confidence outside 0 to 1."""


async def load(store: BaseStore) -> DispatchSetting:
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return DEFAULT
    return DispatchSetting(float(item.value.get("confidence", DEFAULT.confidence)))


async def save(store: BaseStore, setting: DispatchSetting) -> DispatchSetting:
    """Raises DispatchSettingError."""
    if not 0 <= setting.confidence <= 1:
        raise DispatchSettingError("The confidence goes from 0 to 1.")
    await store.aput(_NAMESPACE, _KEY, asdict(setting))
    return setting
