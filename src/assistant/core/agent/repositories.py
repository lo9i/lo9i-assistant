"""Installing skills and MCP servers from a git repository, from any client, and the repositories the
apps list plugins from (the official extras and the ones the user adds). Only the user does this, never
the agent: installed code runs on this computer."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.mcp import McpServerStatus, mcp_status
from assistant.core.mcp.install import FoundServer, ServerField, ServerValues
from assistant.core.repositories import contents, listed, updates
from assistant.core.repositories.contents import RepositoryContents
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.listed import KeptKeys, Repository, RepositoryPlugins
from assistant.core.repositories.updates import PluginUpdate
from assistant.core.skills.store import Skill

__all__ = [
    "FoundServer",
    "InstalledFromRepository",
    "KeptKeys",
    "PluginUpdate",
    "RepositoriesMixin",
    "Repository",
    "RepositoryContents",
    "RepositoryError",
    "RepositoryPlugins",
    "ServerField",
    "ServerValues",
]


@dataclass
class InstalledFromRepository:
    skills: list[Skill]
    servers: list[McpServerStatus]


class RepositoriesMixin(ServiceBase):
    async def browse_repository(self, url: str) -> RepositoryContents:
        """The skills and MCP servers a repository offers, read with its token when it's a private one
        the user added. Raises RepositoryError."""
        store = self._storage.store
        return await contents.browse(store, url, await listed.token(store, self.secrets, url))

    async def install_from_repository(
        self, url: str, skills: list[str], servers: list[ServerValues]
    ) -> InstalledFromRepository:
        """Raises RepositoryError, SkillError or McpServerError, saying what's wrong."""
        store = self._storage.store
        token = await listed.token(store, self.secrets, url)
        installed = await contents.install(store, self.secrets, url, skills, servers, token)
        if installed.skills:
            self.bus.publish("skills")
        if installed.servers:
            await self._servers_changed()
        return InstalledFromRepository(installed.skills, [await mcp_status(self.mcp, s) for s in installed.servers])

    async def repositories(self) -> list[Repository]:
        return await listed.listed(self._storage.store)

    async def add_repository(self, url: str, token: str = "") -> Repository:
        """`token` reads a private repository; it's kept encrypted. Raises RepositoryError when it's
        listed already, can't be read, or offers no plugins."""
        return await listed.add(self._storage.store, self.secrets, url, token)

    async def remove_repository(self, url: str) -> None:
        """Its plugins stay installed. Raises RepositoryError for the extras or one not listed."""
        await listed.remove(self._storage.store, url)

    async def forget_keys(self, kept: KeptKeys) -> None:
        """Delete what a removed plugin left kept, when the user says so."""
        await listed.forget(self._storage.store, kept.plugin, kept.repository)

    async def repository_plugins(self) -> list[RepositoryPlugins]:
        """What every listed repository offers, each saying whether it's installed here from it."""
        return await listed.plugins(self._storage.store, self.secrets)

    async def plugin_updates(self) -> list[PluginUpdate]:
        """Installed plugins their repository has a newer version of, as of the last check."""
        return await updates.available(self._storage.store)

    async def plugin_update_checks(self) -> bool:
        return await updates.checks_enabled(self._storage.store)

    async def set_plugin_update_checks(self, enabled: bool) -> bool:
        await updates.set_checks(self._storage.store, enabled)
        return enabled
