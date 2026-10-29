"""Tells the user when the extras have newer versions of installed plugins, as the web app's badge on
Plugins does: a notification once for each new version found, pointing to /plugins."""

from collections.abc import Callable
from typing import Protocol

from assistant.core.agent import PluginUpdate
from assistant_terminal.i18n import t


class UpdatesSource(Protocol):
    async def updates(self) -> list[PluginUpdate]: ...


class PluginUpdates:
    def __init__(self, repositories: UpdatesSource, notify: Callable[[str], None]) -> None:
        self._repositories = repositories
        self._notify = notify
        self._told: set[PluginUpdate] = set()

    async def refresh(self) -> None:
        found = await self._repositories.updates()
        new = [u for u in found if u not in self._told]
        self._told = set(found)
        if new:
            self._notify(notice(new))


def notice(updates: list[PluginUpdate]) -> str:
    if len(updates) == 1:
        u = updates[0]
        versions = f"{u.installed_version or '-'} → {u.version}"
        return t("Plugin update: {name} {versions}. See /plugins.", name=u.name, versions=versions)
    return t(
        "{count} plugin updates: {names}. See /plugins.", count=len(updates), names=", ".join(u.name for u in updates)
    )
