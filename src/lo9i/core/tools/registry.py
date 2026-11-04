"""Tool registry. Tool modules register themselves at import time; `tools_for` discovers them. Tools in a group
aren't offered until a conversation loads the group, like a plugin's (core/plugin_loading.py): their definitions
would be in every request otherwise, for tools most conversations never use."""

import importlib
import pkgutil
from collections.abc import Callable, Iterable

from langchain_core.tools import BaseTool

_REGISTRY: dict[str, tuple[str, BaseTool]] = {}
# Tools a subagent gets (core/subagent.py): ones that read or work on this computer. Tools that talk
# to the user, change memory, schedule or send are left to the main agent, so a new tool is left out
# unless it says otherwise.
_FOR_SUBAGENTS: set[str] = set()
# The group each tool loaded on demand belongs to, by tool name.
_GROUPS: dict[str, str] = {}

# Tool modules live next to this one.
_PACKAGE = __name__.rpartition(".")[0]


def register(toolset: str, *, subagents: bool = False, group: str = "") -> Callable[[BaseTool], BaseTool]:
    """Add a tool to the registry under a toolset name. With `subagents`, subagents get it too. With `group`, a
    conversation gets it once it loads the group; subagents, which load nothing, get it all the same."""

    def _decorator(tool: BaseTool) -> BaseTool:
        if tool.name in _REGISTRY:
            raise ValueError(f"Tool already registered: {tool.name}")
        _REGISTRY[tool.name] = (toolset, tool)
        if subagents:
            _FOR_SUBAGENTS.add(tool.name)
        if group:
            _GROUPS[tool.name] = group
        return tool

    return _decorator


def tools_for(toolsets: Iterable[str]) -> list[BaseTool]:
    """Tools in the given toolsets, sorted by name so the tool list is stable across calls."""
    _discover()
    wanted = set(toolsets)
    _check_known(wanted)
    return [tool for name, (toolset, tool) in sorted(_REGISTRY.items()) if toolset in wanted]


def offered_tools(toolsets: Iterable[str]) -> list[BaseTool]:
    """The tools of `tools_for` every request offers: those in no group."""
    return [tool for tool in tools_for(toolsets) if tool.name not in _GROUPS]


def tool_groups(toolsets: Iterable[str]) -> dict[str, list[BaseTool]]:
    """The tools of `tools_for` loaded on demand, by group."""
    groups: dict[str, list[BaseTool]] = {}
    for tool in tools_for(toolsets):
        if group := _GROUPS.get(tool.name):
            groups.setdefault(group, []).append(tool)
    return groups


def subagent_tools(toolsets: Iterable[str]) -> list[BaseTool]:
    """The tools of `tools_for` that subagents get."""
    return [tool for tool in tools_for(toolsets) if tool.name in _FOR_SUBAGENTS]


def _discover() -> None:
    package = importlib.import_module(_PACKAGE)
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{_PACKAGE}.{module.name}")


def _check_known(toolsets: set[str]) -> None:
    unknown = toolsets - {toolset for toolset, _ in _REGISTRY.values()}
    if unknown:
        raise ValueError(f"Unknown toolsets: {sorted(unknown)}")
