"""An installed plugin's settings from any client: the values its fields were given, read and changed after it's
installed (core/mcp/plugin_settings.py). Its check runs before they're saved, as when it's installed, and its
processes start again with them."""

import asyncio

from assistant.core.agent.mcp import McpMixin
from assistant.core.mcp import install, keys, plugin_settings, servers
from assistant.core.mcp.install import ServerField
from assistant.core.mcp.plugin_settings import PluginFieldValue, PluginSettings
from assistant.core.mcp.servers import McpServer, McpServerError

__all__ = ["PluginFieldValue", "PluginSettings", "PluginSettingsMixin"]


class PluginSettingsMixin(McpMixin):
    async def plugin_settings(self, name: str) -> PluginSettings:
        """Raises McpServerError for an unknown plugin or a server added by hand, which has no fields."""
        server, fields = await self._with_fields(name)
        return plugin_settings.shown(server, fields)

    async def change_plugin_settings(self, name: str, values: dict[str, str], clear: list[str]) -> PluginSettings:
        """Give its fields new values; one not given keeps its value, a secret given empty too unless it's in
        `clear`. Raises McpServerError for an unknown plugin or field, or a required one left empty, and
        CheckFailedError when its check says they don't work: nothing is saved then."""
        server, fields = await self._with_fields(name)
        change = plugin_settings.changed(server, fields, values, clear)
        await self._plugin_checks.run(change.server, change.cleared)
        await keys.save(self._storage.store, self.secrets, change.server, change.cleared)
        await self._servers_changed()
        return plugin_settings.shown(change.server, fields)

    async def _with_fields(self, name: str) -> tuple[McpServer, list[ServerField]]:
        server = await keys.fill(self._storage.store, self.secrets, await servers.load(self._storage.store, name))
        if not server.source:
            raise McpServerError(f"{name} was added by hand: change its env or headers on the MCP page.")
        return server, await asyncio.to_thread(install.installed_fields, name)
