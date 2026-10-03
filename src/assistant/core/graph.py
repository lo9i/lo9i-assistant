import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.runtime import Runtime

from assistant.core.attachments import hydrate
from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.conversation.digest import Digester
from assistant.core.conversation.epochs import (
    compact,
    is_idle,
    is_renamed,
    is_too_large,
    open_epoch,
    reopen,
    usage_anchor,
)
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.storage import Storage
from assistant.core.tools import tools_for
from assistant.core.usage.meter import TokenMeter

Node = Callable[..., Awaitable[dict]]


class AgentState(MessagesState):
    # The system prompt is built when an epoch starts and reused unchanged until the
    # next one, so the prompt prefix stays byte-identical and the cache keeps hitting.
    system_prompt: str
    epoch_start: int
    epoch_summary: str
    epoch_started_at: str
    last_activity: str
    # Reported token count of the last model call (H3). Cleared when an epoch starts.
    usage_anchor: dict | None
    # The name in this epoch's system prompt; a rename starts a new epoch.
    assistant_name: str
    # Definitions of the MCP tools this epoch offers, frozen when it starts like the system
    # prompt. When the servers' tools change, the next user message starts a new epoch.
    mcp_tools: list[dict[str, Any]]


Graph = CompiledStateGraph[AgentState, Context, AgentState, AgentState]


class McpTools(Protocol):
    """Tools from MCP servers, which come and go while the daemon runs (`core/mcp/hub.py`)."""

    def definitions(self) -> list[dict[str, Any]]: ...

    def tool(self, name: str) -> BaseTool | None: ...


def build_graph(storage: Storage, choice: ModelChoice, digester: Digester, mcp: McpTools) -> Graph:
    tools = tools_for(settings.toolsets)
    builder = StateGraph(AgentState, context_schema=Context)
    builder.add_node("epoch", _epoch_node(digester, mcp))
    llm = metered(build_llm(choice, choice.model), TokenMeter(storage.usage, "reply"))
    builder.add_node("agent", _agent_node(llm, tools))
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=_mcp_calls(mcp)))
    builder.add_edge(START, "epoch")
    builder.add_edge("epoch", "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=storage.checkpointer, store=storage.store)


def _epoch_node(digester: Digester, mcp: McpTools) -> Node:
    """Runs once per user message: opens the first epoch, or starts a new one when needed."""

    async def _epoch(state: AgentState, runtime: Runtime[Context]) -> dict:
        now = datetime.now(UTC)
        update = await _epoch_update(state, runtime, digester, mcp, now)
        if "system_prompt" in update:
            update["mcp_tools"] = mcp.definitions()
        return {**update, "last_activity": now.isoformat()}

    return _epoch


async def _epoch_update(
    state: AgentState, runtime: Runtime[Context], digester: Digester, mcp: McpTools, now: datetime
) -> dict:
    user_id, store = runtime.context.user_id, require_store(runtime.store)
    if not state.get("system_prompt"):
        return await open_epoch(store, user_id, now)
    if is_idle(state, now) or is_too_large(state):
        update = await compact(state, store, user_id, digester, now)
        if update:
            return update
    if await is_renamed(state, store) or state.get("mcp_tools", []) != mcp.definitions():
        return await reopen(state, store, user_id, now)
    return {}


def _mcp_calls(mcp: McpTools) -> AsyncToolCallWrapper:
    """Runs calls to MCP tools, which the tool node doesn't know: they're looked up when called,
    so a tool that was turned off or whose server went away stops working at once."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        if request.tool is None and (tool := mcp.tool(request.tool_call["name"])) is not None:
            request = request.override(tool=tool)
        return await execute(request)

    return _wrap


def _agent_node(llm: BaseChatModel, tools: Sequence[BaseTool]) -> Node:
    async def _agent(state: AgentState) -> dict:
        epoch = state["messages"][state.get("epoch_start", 0) :]
        messages = await asyncio.to_thread(hydrate, epoch)
        bound = llm.bind_tools([*tools, *state.get("mcp_tools", [])])
        response = await bound.ainvoke([SystemMessage(state["system_prompt"]), *messages])
        return {"messages": [response], "usage_anchor": usage_anchor(response, len(state["messages"]) + 1)}

    return _agent
