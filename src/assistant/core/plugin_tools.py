"""The tools plugins bring, which come and go while the daemon runs: MCP servers' tools (core/mcp/hub.py)
and, while a coding agent plugin is installed, the task tools (core/agent_tasks/tools.py). The graph
freezes their definitions per epoch and looks each one up when it's called (core/graph.py)."""

from typing import Any

from langchain_core.tools import BaseTool

from assistant.core.agent_tasks.tools import AgentTools
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.sanitize import MCP_PREFIX


class PluginTools:
    def __init__(self, mcp: McpHub, agents: AgentTools) -> None:
        self._mcp = mcp
        self._agents = agents

    def definitions(self) -> list[dict[str, Any]]:
        return [*self._mcp.definitions(), *self._agents.definitions()]

    def read_only_definitions(self) -> list[dict[str, Any]]:
        """For subagents: the task tools start and stop work, so only MCP tools that say they only read."""
        return self._mcp.read_only_definitions()

    def tool(self, name: str) -> BaseTool | None:
        return self._mcp.tool(name) or self._agents.tool(name)

    def offered(self, name: str) -> bool:
        """A tool an epoch may have offered from a plugin, whether or not it can run now."""
        return name.startswith(MCP_PREFIX) or self._agents.offers(name)

    def unavailable(self, name: str) -> str:
        """Why a tool this epoch offers can't run now, for the model."""
        if self._agents.offers(name):
            return f"{name} isn't available: no coding agent plugin is installed and turned on now."
        return self._mcp.unavailable(name)
