"""Tools the agent uses to manage long-term memories about the user."""

from uuid import uuid4

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context
from assistant.core.tools.registry import register


def namespace(user_id: str) -> tuple[str, ...]:
    return ("memories", user_id)


@register("memory")
@tool
async def remember(fact: str, runtime: ToolRuntime[Context]) -> str:
    """Save a durable fact about the user (preference, detail, ongoing goal) for future conversations."""
    memory_id = uuid4().hex[:8]
    await runtime.store.aput(namespace(runtime.context.user_id), memory_id, {"fact": fact})
    return f"Saved as {memory_id}."


@register("memory")
@tool
async def forget(memory_id: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a saved memory that is wrong or outdated, by its id."""
    await runtime.store.adelete(namespace(runtime.context.user_id), memory_id)
    return f"Deleted {memory_id}."
