"""Installing skills and MCP servers from a git repository, from any client. Only the user does
this, never the agent: installed code runs on this computer."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.mcp import McpServerStatus, mcp_status
from assistant.core.mcp.install import FoundServer, ServerField, ServerValues
from assistant.core.repositories import contents, updates
from assistant.core.repositories.contents import RepositoryContents
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.updates import PluginUpdate
from assistant.core.skills.store import Skill

__all__ = [
    "FoundServer",
    "InstalledFromRepository",
    "PluginUpdate",
    "RepositoriesMixin",
    "RepositoryContents",
    "RepositoryError",
    "ServerField",
    "ServerValues",
]


@dataclass
class InstalledFromRepository:
    skills: list[Skill]
    servers: list[McpServerStatus]


class RepositoriesMixin(ServiceBase):
    async def browse_repository(self, url: str) -> RepositoryContents:
        """The skills and MCP servers a repository offers. Raises RepositoryError."""
        return await contents.browse(self._storage.store, url)

    async def install_from_repository(
        self, url: str, skills: list[str], servers: list[ServerValues]
    ) -> InstalledFromRepository:
        """Raises RepositoryError, SkillError or McpServerError, saying what's wrong."""
        installed = await contents.install(self._storage.store, url, skills, servers)
        if installed.skills:
            self.bus.publish("skills")
        if installed.servers:
            await self._servers_changed()
        return InstalledFromRepository(installed.skills, [await mcp_status(self.mcp, s) for s in installed.servers])

    async def plugin_updates(self) -> list[PluginUpdate]:
        """Installed plugins the extras have a newer version of, as of the last check."""
        return await updates.available(self._storage.store)

    async def plugin_update_checks(self) -> bool:
        return await updates.checks_enabled(self._storage.store)

    async def set_plugin_update_checks(self, enabled: bool) -> bool:
        await updates.set_checks(self._storage.store, enabled)
        return enabled
