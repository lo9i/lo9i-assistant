"""The tools each MCP server had when it last connected, kept in the Store, so a server that starts on its
first use (core/mcp/connection.py, OnDemand) offers its tools while it isn't running."""

from langgraph.store.base import BaseStore
from mcp.types import Tool

_NAMESPACE = ("mcp_tools",)


async def load(store: BaseStore, name: str) -> list[Tool]:
    """[] when the server never connected, or its tools were forgotten."""
    item = await store.aget(_NAMESPACE, name)
    return [Tool.model_validate(tool) for tool in item.value["tools"]] if item else []


async def save(store: BaseStore, name: str, tools: list[Tool]) -> None:
    await store.aput(_NAMESPACE, name, {"tools": [t.model_dump(mode="json", by_alias=True) for t in tools]})


async def forget(store: BaseStore, name: str) -> None:
    await store.adelete(_NAMESPACE, name)
