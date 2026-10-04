"""Tool registry. Tool modules register themselves at import time; `tools_for` discovers them."""

import importlib
import pkgutil
from collections.abc import Callable, Iterable

from langchain_core.tools import BaseTool

_REGISTRY: dict[str, tuple[str, BaseTool]] = {}
# Tools a subagent gets (core/subagent.py): ones that read or work on this computer. Tools that talk
# to the user, change memory, schedule or send are left to the main agent, so a new tool is left out
# unless it says otherwise.
_FOR_SUBAGENTS: set[str] = set()

# Tool modules live next to this one.
_PACKAGE = __name__.rpartition(".")[0]


def register(toolset: str, *, subagents: bool = False) -> Callable[[BaseTool], BaseTool]:
    """Add a tool to the registry under a toolset name. With `subagents`, subagents get it too."""

    def _decorator(tool: BaseTool) -> BaseTool:
        if tool.name in _REGISTRY:
            raise ValueError(f"Tool already registered: {tool.name}")
        _REGISTRY[tool.name] = (toolset, tool)
        if subagents:
            _FOR_SUBAGENTS.add(tool.name)
        return tool

    return _decorator


def tools_for(toolsets: Iterable[str]) -> list[BaseTool]:
    """Tools in the given toolsets, sorted by name so the tool list is stable across calls."""
    _discover()
    wanted = set(toolsets)
    _check_known(wanted)
    return [tool for name, (toolset, tool) in sorted(_REGISTRY.items()) if toolset in wanted]


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
