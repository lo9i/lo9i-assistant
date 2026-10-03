"""Installed plugins the extras have a newer version of, and the setting that turns checking for them
on and off (Settings → General), one Store record. Read from the extras' kept listing (cache.py),
without reaching the repository; checker.py keeps that listing fresh."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from assistant.core.repositories import contents
from assistant.core.repositories.known import EXTRAS

_NAMESPACE = ("settings",)
_KEY = "plugin_updates"


@dataclass(frozen=True)
class PluginUpdate:
    kind: str  # server | skill
    name: str
    installed_version: str
    version: str


async def available(store: BaseStore) -> list[PluginUpdate]:
    """Empty while checks are off; the Plugins page still shows each plugin's versions."""
    offered = await contents.kept(store, EXTRAS) if await checks_enabled(store) else None
    if offered is None:
        return []
    found = [("server", s) for s in offered.servers] + [("skill", s) for s in offered.skills]
    return [
        PluginUpdate(kind, f.name, f.installed_version, f.version)
        for kind, f in found
        if f.installed and f.version and f.version != f.installed_version
    ]


async def checks_enabled(store: BaseStore) -> bool:
    item = await store.aget(_NAMESPACE, _KEY)
    return bool(item.value.get("enabled", True)) if item else True


async def set_checks(store: BaseStore, enabled: bool) -> None:
    await store.aput(_NAMESPACE, _KEY, {"enabled": enabled})
