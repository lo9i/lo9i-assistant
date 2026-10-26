"""Plugins' tools load on demand. Their definitions are most of a request, so an epoch starts with the core
tools, the task tools and load_tools, and the system prompt lists the plugins with their tools' names
(conversation/prompt.py). A round of tool calls loads a plugin for the rest of the epoch when it calls
load_tools for it, uses a skill that comes with it, installs it from offer_plugin, or calls one of its tools
anyway (a call runs whether or not its plugin is loaded, core/graph.py::mcp_calls); an epoch starts with
its pinned skills' plugins loaded, and a scheduled run's with the plugins its job names. The graph keeps the loaded
plugins and their definitions in state."""

import asyncio
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Annotated

from langchain_core.messages import ToolCall
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from assistant.core.skills import store as skills
from assistant.core.skills.store import SkillError

LOAD_TOOLS = "load_tools"

# Each plugin with tools, and their names without its prefix (core/mcp/hub.py::catalog).
Catalog = Mapping[str, Sequence[str]]

_MCP_TOOL = re.compile(r"mcp__(\S+?)__")

_DESCRIPTION = (
    "Load a plugin's tools (see Plugin tools) when the user's request needs them. They're yours from your next "
    "step for the rest of the conversation. use_skill with a plugin's skill loads them too."
)


class _Load(BaseModel):
    plugin: Annotated[str, Field(description="The plugin's name, as Plugin tools lists it")]


def load_tools(catalog: Callable[[], Catalog]) -> BaseTool:
    """The tool only answers; the graph loads what a round of calls asks for (`requested`)."""

    async def _load(plugin: str) -> str:
        tools = catalog().get(plugin)
        if tools is None:
            return f"No plugin named {plugin} has tools. Plugins: {', '.join(catalog()) or 'none'}."
        return f"Loaded the tools of {plugin} ({', '.join(tools)}): they're yours from your next step."

    return StructuredTool.from_function(coroutine=_load, name=LOAD_TOOLS, description=_DESCRIPTION, args_schema=_Load)


async def requested(calls: Sequence[ToolCall], catalog: Catalog, plugin_of: Callable[[str], str | None]) -> set[str]:
    """The plugins a round of tool calls loads, among those in `catalog`."""
    found: set[str] = set()
    for call in calls:
        found |= await _requested(call, plugin_of)
    return {plugin for plugin in found if plugin in catalog}


async def _requested(call: ToolCall, plugin_of: Callable[[str], str | None]) -> set[str]:
    name, args = call["name"], call["args"]
    if name == LOAD_TOOLS:
        return {str(args.get("plugin", ""))}
    if name == "offer_plugin":
        return {str(args.get("name", ""))}
    if name == "use_skill":
        return await skill_plugins([str(args.get("name", ""))])
    plugin = plugin_of(name)
    return {plugin} if plugin else set()


async def skill_plugins(names: Iterable[str]) -> set[str]:
    """The MCP servers these skills come with."""
    found: set[str] = set()
    for name in names:
        try:
            skill = await asyncio.to_thread(skills.load, name)
        except SkillError:
            continue
        if skill.server:
            found.add(skill.server)
    return found


async def named(text: str) -> set[str]:
    """The plugins a job's task names: one of its tools (mcp__<server>__<tool>), or a skill that comes with it."""
    found = {match[1] for match in _MCP_TOOL.finditer(text)}
    listed = await asyncio.to_thread(skills.list_skills)
    return found | {skill.server for skill in listed if skill.server and _mentions(text, skill.name)}


def _mentions(text: str, name: str) -> bool:
    """`name` as a word of its own: news-digest in "Run the skill news-digest", not news in "newsletter"."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None
