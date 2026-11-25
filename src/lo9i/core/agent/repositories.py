"""Installing skills and MCP servers from a git repository, from any client, and the repositories the
apps list plugins from (the official extras and the ones the user adds). Only the user does this, never
the agent: installed code runs on this computer."""

from dataclasses import dataclass

from lo9i.core.agent.base import ServiceBase
from lo9i.core.agent.mcp import McpServerStatus, mcp_status
from lo9i.core.config import settings
from lo9i.core.mcp import owner_approval, plugin_oauth
from lo9i.core.mcp.install import FoundServer, ServerField, ServerValues
from lo9i.core.mcp.servers import McpServer
from lo9i.core.repositories import contents, listed, updates
from lo9i.core.repositories.contents import RepositoryContents
from lo9i.core.repositories.errors import RepositoryError
from lo9i.core.repositories.listed import KeptKeys, Repository, RepositoryPlugins
from lo9i.core.repositories.updates import PluginUpdate
from lo9i.core.skills.store import Skill

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
        self, url: str, skills: list[str], servers: list[ServerValues], asked_by: str | None = None
    ) -> InstalledFromRepository:
        """`asked_by` names the paired device asking, None for the owner on this computer. Raises RepositoryError,
        SkillError or McpServerError, saying what's wrong: CheckFailedError when a server's check says the values it
        was given don't work (core/mcp/checks.py), NotApprovedError when the owner doesn't approve a device's
        install of code that runs here (core/mcp/owner_approval.py)."""
        store = self._storage.store
        token = await listed.token(store, self.secrets, url)
        approve = self._install_approval(url, asked_by) if asked_by is not None else None
        installed = await contents.install(
            store, self.secrets, url, skills, servers, token, self._plugin_checks.run, approve
        )
        if installed.skills:
            self.bus.publish("skills")
        if installed.servers:
            await self._servers_changed()
        statuses = [
            await mcp_status(self.mcp, s, await plugin_oauth.signed_in_as(store, self.secrets, s))
            for s in installed.servers
        ]
        return InstalledFromRepository(installed.skills, statuses)

    async def repositories(self) -> list[Repository]:
        return await listed.listed(self._storage.store)

    async def add_repository(self, url: str, token: str = "", asked_by: str | None = None) -> Repository:
        """`token` reads a private repository; it's kept encrypted. `asked_by` names the paired device asking, None
        for the owner on this computer. Raises RepositoryError when it's listed already, can't be read, or offers no
        plugins, NotApprovedError when the owner doesn't approve a device adding it."""
        if asked_by is not None:
            await self._owner_approves_repository(owner_approval.repository(url.strip(), asked_by), asked_by)
        return await listed.add(self._storage.store, self.secrets, url, token)

    def _install_approval(self, url: str, device: str) -> contents.Approve:
        """Asks the owner when what a device installs runs code here: a plugin's processes, a skill's scripts."""

        async def approve(plugins: list[McpServer], skills: list[Skill]) -> None:
            running = [p for p in plugins if owner_approval.runs_code(p)]
            scripted = [s for s in skills if s.files]
            if running or scripted:
                await self._owner_approves_repository(
                    owner_approval.repository_install(url, running, scripted, device), device
                )

        return approve

    async def _owner_approves_repository(self, request: owner_approval.Request, device: str) -> None:
        await owner_approval.ask(self.approvals, request, device, settings.job_approval_minutes)

    async def remove_repository(self, url: str) -> None:
        """Its plugins stay installed. Raises RepositoryError for the extras or one not listed."""
        await listed.remove(self._storage.store, url)

    async def kept_keys(self) -> list[KeptKeys]:
        """Everything removed plugins left kept: their keys, and private repositories' tokens."""
        return await listed.kept(self._storage.store)

    async def forget_keys(self, kept: KeptKeys) -> None:
        """Delete what a removed plugin left kept, when the user says so."""
        await listed.forget(self._storage.store, kept.plugin, kept.repository)

    async def repository_plugins(self, cached: bool = False) -> list[RepositoryPlugins]:
        """What every listed repository offers, each saying whether it's installed here from it.
        `cached`: as each repository offered it when last read, reaching only those never read."""
        return await listed.plugins(self._storage.store, self.secrets, cached)

    async def plugin_updates(self) -> list[PluginUpdate]:
        """Installed plugins their repository has a newer version of, as of the last check."""
        return await updates.available(self._storage.store)

    async def plugin_update_checks(self) -> bool:
        return await updates.checks_enabled(self._storage.store)

    async def set_plugin_update_checks(self, enabled: bool) -> bool:
        await updates.set_checks(self._storage.store, enabled)
        return enabled
