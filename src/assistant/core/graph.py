import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Send

from assistant.core.attachments import hydrate
from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.conversation.epochs import (
    compact,
    is_idle,
    is_renamed,
    is_repinned,
    is_too_large,
    open_epoch,
    reopen,
    usage_anchor,
)
from assistant.core.conversation.summary import Summarizer
from assistant.core.conversation.trim import trim_update, trimmed
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.providers import IMAGES_IN_TOOL_RESULTS
from assistant.core.mcp.sanitize import MCP_PREFIX
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
    # When the last model call was, and before which message tool results are sent as stubs
    # (conversation/trim.py).
    last_model_call: str
    trimmed_before: int
    # The name in this epoch's system prompt; a rename starts a new epoch.
    assistant_name: str
    # The skills pinned to this conversation when the epoch started (conversation/pinned.py), in full in
    # its system prompt; pinning or unpinning one starts a new epoch.
    pinned_skills: list[str]
    # Definitions of the MCP tools this epoch offers, frozen when it starts like the system
    # prompt. When the servers' tools change, the next user message starts a new epoch.
    mcp_tools: list[dict[str, Any]]


Graph = CompiledStateGraph[AgentState, Context, AgentState, AgentState]


class McpTools(Protocol):
    """Tools from MCP servers, which come and go while the daemon runs (`core/mcp/hub.py`)."""

    def definitions(self) -> list[dict[str, Any]]: ...

    def read_only_definitions(self) -> list[dict[str, Any]]: ...

    def tool(self, name: str) -> BaseTool | None: ...

    def unavailable(self, name: str) -> str: ...


def build_graph(storage: Storage, choice: ModelChoice, summarizer: Summarizer, mcp: McpTools) -> Graph:
    tools = tools_for(settings.toolsets)
    builder = StateGraph(AgentState, context_schema=Context)
    builder.add_node("epoch", _epoch_node(summarizer, mcp))
    llm = metered(build_llm(choice, choice.model), TokenMeter(storage.usage, "reply"))
    builder.add_node("agent", _agent_node(llm, tools, choice.provider in IMAGES_IN_TOOL_RESULTS))
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=mcp_calls(mcp)))
    builder.add_edge(START, "epoch")
    builder.add_edge("epoch", "agent")
    builder.add_conditional_edges("agent", each_tool_call("tools"), ["tools", END])
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=storage.checkpointer, store=storage.store)


def _epoch_node(summarizer: Summarizer, mcp: McpTools) -> Node:
    """Runs once per user message: opens the first epoch, or starts a new one when needed."""

    async def _epoch(state: AgentState, runtime: Runtime[Context], config: RunnableConfig) -> dict:
        now = datetime.now(UTC)
        thread_id = config.get("configurable", {})["thread_id"]
        trim = trim_update(state, now)
        update = await _epoch_update(cast(AgentState, {**state, **trim}), runtime, thread_id, summarizer, mcp, now)
        if "system_prompt" in update:
            update["mcp_tools"] = mcp.definitions()
        return {**trim, **update, "last_activity": now.isoformat()}

    return _epoch


async def _epoch_update(
    state: AgentState, runtime: Runtime[Context], thread_id: str, summarizer: Summarizer, mcp: McpTools, now: datetime
) -> dict:
    user_id, store = runtime.context.user_id, require_store(runtime.store)
    if not state.get("system_prompt"):
        return await open_epoch(store, user_id, thread_id, now)
    if is_idle(state, now) or is_too_large(state):
        update = await compact(state, store, user_id, thread_id, summarizer, now)
        if update:
            return update
    if await _prompt_changed(state, store, user_id, thread_id, mcp):
        return await reopen(state, store, user_id, thread_id, now)
    return {}


async def _prompt_changed(state: AgentState, store: BaseStore, user_id: str, thread_id: str, mcp: McpTools) -> bool:
    """What the epoch's system prompt or tools were built from changed: the name, the pinned skills
    or the MCP tools."""
    if await is_renamed(state, store) or await is_repinned(state, store, user_id, thread_id):
        return True
    return state.get("mcp_tools", []) != mcp.definitions()


def each_tool_call(node: str) -> Callable[[MessagesState], str | list[Send]]:
    """Routes each tool call of the last reply to `node` as a task of its own. Subagents started by
    parallel delegate calls then keep their checkpoints apart, so each pauses and resumes for its own
    approvals (core/subagent.py)."""

    def _route(state: MessagesState) -> str | list[Send]:
        last = state["messages"][-1]
        calls = last.tool_calls if isinstance(last, AIMessage) else []
        return [Send(node, [call]) for call in calls] or END

    return _route


def mcp_calls(mcp: McpTools) -> AsyncToolCallWrapper:
    """Runs calls to MCP tools, which the tool node doesn't know: they're looked up when called,
    so a tool that was turned off or whose server went away stops working at once."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        if request.tool is not None:
            return await execute(request)
        name = request.tool_call["name"]
        if (tool := mcp.tool(name)) is not None:
            return await execute(request.override(tool=tool))
        if name.startswith(MCP_PREFIX):
            return ToolMessage(mcp.unavailable(name), tool_call_id=request.tool_call["id"], name=name, status="error")
        return await execute(request)

    return _wrap


def _agent_node(llm: BaseChatModel, tools: Sequence[BaseTool], images_in_tool_results: bool) -> Node:
    async def _agent(state: AgentState) -> dict:
        epoch = trimmed(state["messages"], state.get("epoch_start", 0), state.get("trimmed_before", 0))
        messages = await asyncio.to_thread(hydrate, epoch, images_in_tool_results)
        bound = llm.bind_tools([*tools, *state.get("mcp_tools", [])])
        response = await bound.ainvoke([SystemMessage(state["system_prompt"]), *messages])
        return {
            "messages": [response],
            "usage_anchor": usage_anchor(response, len(state["messages"]) + 1),
            "last_model_call": datetime.now(UTC).isoformat(),
        }

    return _agent
