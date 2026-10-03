"""Installing skills and MCP servers from a git repository, from any client. Only the user does
this, never the agent: installed code runs on this computer."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.mcp import McpServerStatus, mcp_status
from assistant.core.mcp.install import FoundServer, ServerField, ServerValues
from assistant.core.repositories import contents
from assistant.core.repositories.contents import RepositoryContents
from assistant.core.repositories.errors import RepositoryError
from assistant.core.skills.store import Skill

__all__ = [
    "FoundServer",
    "InstalledFromRepository",
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
        return await contents.browse(url)

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
