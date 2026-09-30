"""Tool registry. Tool modules register themselves at import time; `tools_for` discovers them."""

import importlib
import pkgutil
from collections.abc import Callable, Iterable

from langchain_core.tools import BaseTool

_REGISTRY: dict[str, tuple[str, BaseTool]] = {}

# Tool modules live next to this one.
_PACKAGE = __name__.rpartition(".")[0]


def register(toolset: str) -> Callable[[BaseTool], BaseTool]:
    """Add a tool to the registry under a toolset name."""

    def _decorator(tool: BaseTool) -> BaseTool:
        if tool.name in _REGISTRY:
            raise ValueError(f"Tool already registered: {tool.name}")
        _REGISTRY[tool.name] = (toolset, tool)
        return tool

    return _decorator


def tools_for(toolsets: Iterable[str]) -> list[BaseTool]:
    """Tools in the given toolsets, sorted by name so the tool list is stable across calls."""
    _discover()
    wanted = set(toolsets)
    _check_known(wanted)
    return [tool for name, (toolset, tool) in sorted(_REGISTRY.items()) if toolset in wanted]


def _discover() -> None:
    package = importlib.import_module(_PACKAGE)
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{_PACKAGE}.{module.name}")


def _check_known(toolsets: set[str]) -> None:
    unknown = toolsets - {toolset for toolset, _ in _REGISTRY.values()}
    if unknown:
        raise ValueError(f"Unknown toolsets: {sorted(unknown)}")
