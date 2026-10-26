"""The tools plugins bring, which come and go while the daemon runs: MCP servers' tools (core/mcp/hub.py),
loaded by a conversation when it needs them (core/plugin_loading.py), and, while a coding agent plugin is
installed, the task tools (core/agent_tasks/tools.py). The graph keeps their definitions per epoch and looks
each one up when it's called (core/graph.py)."""

from collections.abc import Collection
from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from assistant.core.agent_tasks.tools import AgentTools
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.sanitize import MCP_PREFIX
from assistant.core.plugin_loading import LOAD_TOOLS, load_tools


class PluginTools:
    def __init__(self, mcp: McpHub, agents: AgentTools) -> None:
        self._mcp = mcp
        self._agents = agents
        self._load = load_tools(self._mcp.catalog)

    def definitions(self, loaded: Collection[str]) -> list[dict[str, Any]]:
        """What an epoch offers: load_tools while a plugin has tools, the task tools, and the tools of the
        plugins in `loaded`."""
        loading = [convert_to_openai_tool(self._load)] if self._mcp.catalog() else []
        return [*loading, *self._agents.definitions(), *self._mcp.definitions(loaded)]

    def read_only_definitions(self) -> list[dict[str, Any]]:
        """For subagents, which keep those of the plugins their conversation loaded: the task tools start and stop
        work, so only MCP tools that say they only read."""
        return self._mcp.read_only_definitions()

    def catalog(self) -> dict[str, list[str]]:
        return self._mcp.catalog()

    def plugin_of(self, name: str) -> str | None:
        return self._mcp.server_of(name)

    def tool(self, name: str) -> BaseTool | None:
        if name == LOAD_TOOLS:
            return self._load if self._mcp.catalog() else None
        return self._mcp.tool(name) or self._agents.tool(name)

    def offered(self, name: str) -> bool:
        """A tool an epoch may have offered from a plugin, whether or not it can run now."""
        return name == LOAD_TOOLS or name.startswith(MCP_PREFIX) or self._agents.offers(name)

    def unavailable(self, name: str) -> str:
        """Why a tool this epoch offers can't run now, for the model."""
        if name == LOAD_TOOLS:
            return f"{name} isn't available: no plugin with tools is installed and turned on now."
        if self._agents.offers(name):
            return f"{name} isn't available: no coding agent plugin is installed and turned on now."
        return self._mcp.unavailable(name)
