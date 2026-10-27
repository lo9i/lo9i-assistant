"""The tools a conversation loads when it needs them (core/plugin_loading.py), and those plugins bring: MCP servers'
tools (core/mcp/hub.py), the groups of the assistant's own tools loaded the same way (email, jobs, skill writing:
core/tools/registry.py, listed and loaded like a plugin's), and, while a coding agent plugin is installed, the task
tools (core/agent_tasks/tools.py). The graph keeps their definitions per epoch and looks each plugin's up when it's
called (core/graph.py); the assistant's own run as any core tool."""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from assistant.core.agent_tasks.tools import AgentTools
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.sanitize import MCP_PREFIX
from assistant.core.plugin_loading import LOAD_TOOLS, load_tools


class PluginTools:
    def __init__(self, mcp: McpHub, agents: AgentTools, groups: Mapping[str, Sequence[BaseTool]]) -> None:
        """`groups`: the assistant's own tools loaded on demand, by group. A group is listed under its name, over a
        server of the same name."""
        self._mcp = mcp
        self._agents = agents
        self._groups = {group: [convert_to_openai_tool(t) for t in tools] for group, tools in groups.items()}
        self._group_of = {tool.name: group for group, tools in groups.items() for tool in tools}
        self._load = load_tools(self.catalog)

    def definitions(self, loaded: Collection[str]) -> list[dict[str, Any]]:
        """What an epoch offers: load_tools while there's something to load, the task tools, and the tools of the
        plugins and groups in `loaded`."""
        loading = [convert_to_openai_tool(self._load)] if self.catalog() else []
        own = [d for group in sorted(self._groups) if group in loaded for d in self._groups[group]]
        mcp = self._mcp.definitions([p for p in loaded if p not in self._groups])
        return [*loading, *self._agents.definitions(), *own, *mcp]

    def read_only_definitions(self) -> list[dict[str, Any]]:
        """For subagents, which keep those of the plugins their conversation loaded: the task tools start and stop
        work, so only MCP tools that say they only read."""
        return self._mcp.read_only_definitions()

    def catalog(self) -> dict[str, list[str]]:
        own = {group: [d["function"]["name"] for d in tools] for group, tools in self._groups.items()}
        return {**self._mcp.catalog(), **own}

    def plugin_of(self, name: str) -> str | None:
        """The plugin or group whose tool `name` is."""
        return self._group_of.get(name) or self._mcp.server_of(name)

    def tool(self, name: str) -> BaseTool | None:
        if name == LOAD_TOOLS:
            return self._load if self.catalog() else None
        return self._mcp.tool(name) or self._agents.tool(name)

    def offered(self, name: str) -> bool:
        """A tool an epoch may have offered from a plugin, whether or not it can run now."""
        return name == LOAD_TOOLS or name.startswith(MCP_PREFIX) or self._agents.offers(name)

    def unavailable(self, name: str) -> str:
        """Why a tool this epoch offers can't run now, for the model."""
        if name == LOAD_TOOLS:
            return f"{name} isn't available: there's nothing to load now."
        if self._agents.offers(name):
            return f"{name} isn't available: no coding agent plugin is installed and turned on now."
        return self._mcp.unavailable(name)
