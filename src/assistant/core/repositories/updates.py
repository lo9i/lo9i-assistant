"""Installed plugins their repository has a newer version of, and the setting that turns checking for
them on and off (Settings → General), one Store record. Read from each listed repository's kept listing
(cache.py, listed.py), without reaching them; checker.py keeps those listings fresh."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from assistant.core.repositories import contents, listed

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
    if not await checks_enabled(store):
        return []
    found = []
    for repository in await listed.listed(store):
        offered = await contents.kept(store, repository.url)
        if offered is not None:
            found += [("server", s) for s in offered.servers] + [("skill", s) for s in offered.skills]
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
