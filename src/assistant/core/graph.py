import asyncio
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolCall, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Send

from assistant.core import plugin_loading
from assistant.core.attachments import hydrate
from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.conversation.dispatch import build_classifier
from assistant.core.conversation.dispatch_nodes import ASK, DISPATCH, SEND, dispatch_nodes
from assistant.core.conversation.epochs import (
    compact,
    is_idle,
    is_renamed,
    is_repinned,
    is_reworded,
    is_too_large,
    open_epoch,
    reopen,
    usage_anchor,
)
from assistant.core.conversation.routed import without_routed
from assistant.core.conversation.summary import Summarizer
from assistant.core.conversation.trim import trim_update, trimmed
from assistant.core.conversation.unanswered import answered
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice, prompt_cache_minutes
from assistant.core.llm.providers import IMAGES_IN_TOOL_RESULTS
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
    # Reported token count of the last model call. Cleared when an epoch starts.
    usage_anchor: dict | None
    # When the last model call was, and before which message tool results are sent as stubs
    # (conversation/trim.py).
    last_model_call: str
    trimmed_before: int
    # The name in this epoch's system prompt; a rename starts a new epoch.
    assistant_name: str
    # Where a message in the inbox is going on while it's being routed (conversation/dispatch_nodes.py).
    dispatching: dict | None
    # The inbox's quick exchange in progress: the index of its first message and the user's turns in it.
    inbox_exchange: dict | None
    # The skills pinned to this conversation when the epoch started (conversation/pinned.py), in full in
    # its system prompt; pinning or unpinning one starts a new epoch.
    pinned_skills: list[str]
    # A digest of the prompt texts the user can edit (conversation/prompt_edits.py) this epoch's system
    # prompt was built with; an edit starts a new epoch.
    prompt_texts: str
    # Definitions of the plugins' tools this epoch offers (core/plugin_tools.py): load_tools, the task tools
    # and the tools of the plugins it loaded, which change only when it loads one (_loaded_node). When the
    # plugins' tools change, the next user message starts a new epoch, or right after offer_plugin when the
    # user installed a server.
    mcp_tools: list[dict[str, Any]]
    # The plugins whose tools this epoch loaded (core/plugin_loading.py). A new epoch at the same point keeps
    # them; one that summarizes keeps those its kept turns called (_kept_plugins).
    loaded_plugins: list[str]
    # Each plugin with tools and their names, as this epoch's system prompt lists them.
    plugin_tools: dict[str, list[str]]


Graph = CompiledStateGraph[AgentState, Context, AgentState, AgentState]


class McpTools(Protocol):
    """Tools from plugins, which come and go while the daemon runs (`core/plugin_tools.py`)."""

    def definitions(self, loaded: Collection[str]) -> list[dict[str, Any]]: ...

    def catalog(self) -> dict[str, list[str]]: ...

    def plugin_of(self, name: str) -> str | None: ...

    def read_only_definitions(self) -> list[dict[str, Any]]: ...

    def tool(self, name: str) -> BaseTool | None: ...

    def offered(self, name: str) -> bool: ...

    def unavailable(self, name: str) -> str: ...


def build_graph(storage: Storage, choice: ModelChoice, summarizer: Summarizer, mcp: McpTools) -> Graph:
    tools = tools_for(settings.toolsets)
    builder = StateGraph(AgentState, context_schema=Context)
    builder.add_node("epoch", _epoch_node(summarizer, mcp, prompt_cache_minutes(choice)))
    llm = metered(build_llm(choice, choice.model), TokenMeter(storage.usage, "reply"))
    builder.add_node("agent", _agent_node(llm, tools, choice.provider in IMAGES_IN_TOOL_RESULTS))
    builder.add_node("tools", ToolNode(tools, awrap_tool_call=mcp_calls(mcp)))
    builder.add_node("installed", _loaded_node(mcp))
    dispatch = dispatch_nodes(build_classifier(choice, storage.usage), then="epoch")
    builder.add_node(DISPATCH, dispatch[DISPATCH], destinations=("epoch", ASK, SEND))
    builder.add_node(ASK, dispatch[ASK], destinations=(SEND,))
    builder.add_node(SEND, dispatch[SEND], destinations=(END,))
    builder.add_edge(START, DISPATCH)
    builder.add_edge("epoch", "agent")
    builder.add_conditional_edges("agent", each_tool_call("tools"), ["tools", END])
    builder.add_edge("tools", "installed")
    builder.add_edge("installed", "agent")
    return builder.compile(checkpointer=storage.checkpointer, store=storage.store)


def _epoch_node(summarizer: Summarizer, mcp: McpTools, cache_minutes: float) -> Node:
    """Runs once per user message: opens the first epoch, or starts a new one when needed, and trims old
    tool results once the model's prompt cache, which lasts `cache_minutes`, has expired."""

    async def _epoch(state: AgentState, runtime: Runtime[Context], config: RunnableConfig) -> dict:
        now = datetime.now(UTC)
        thread_id = config.get("configurable", {})["thread_id"]
        trim = trim_update(state, now, cache_minutes)
        catalog = mcp.catalog()
        update = await _epoch_update(
            cast(AgentState, {**state, **trim}), runtime, thread_id, summarizer, mcp, catalog, now
        )
        if "system_prompt" in update:
            named = await _named_plugins(state, runtime)
            update |= await _plugins_update(state, update, mcp, catalog, named)
        return {**trim, **update, "last_activity": now.isoformat()}

    return _epoch


async def _epoch_update(
    state: AgentState,
    runtime: Runtime[Context],
    thread_id: str,
    summarizer: Summarizer,
    mcp: McpTools,
    catalog: dict[str, list[str]],
    now: datetime,
) -> dict:
    user_id, store = runtime.context.user_id, require_store(runtime.store)
    if not state.get("system_prompt"):
        return await open_epoch(store, user_id, thread_id, now, catalog)
    if is_idle(state, now) or is_too_large(state):
        update = await compact(state, store, user_id, thread_id, summarizer, now, catalog)
        if update:
            return update
    if await _prompt_changed(state, store, user_id, thread_id, mcp, catalog):
        return await reopen(state, store, user_id, thread_id, now, catalog)
    return {}


async def _plugins_update(
    state: AgentState, epoch: dict, mcp: McpTools, catalog: dict[str, list[str]], named: set[str]
) -> dict:
    """The plugins' tools a new epoch starts with: its pinned skills' plugins, those it keeps and those `named`."""
    pinned = await plugin_loading.skill_plugins(epoch["pinned_skills"])
    wanted = {*_kept_plugins(state, epoch, mcp), *pinned, *named}
    loaded = sorted(plugin for plugin in wanted if plugin in catalog)
    return {"loaded_plugins": loaded, "mcp_tools": mcp.definitions(loaded), "plugin_tools": catalog}


async def _named_plugins(state: AgentState, runtime: Runtime[Context]) -> set[str]:
    """A scheduled run's: the plugins its job names in its message, so it doesn't spend a step loading them."""
    if not runtime.context.unattended or not state["messages"]:
        return set()
    return await plugin_loading.named(state["messages"][-1].text)


def _kept_plugins(state: AgentState, epoch: dict, mcp: McpTools) -> set[str]:
    """At the same point (nothing summarized, `epoch_start` stays) the plugins loaded before; after a summary,
    those whose tools the turns it keeps called, so the work in progress goes on with them."""
    if "epoch_start" not in epoch:
        return set(state.get("loaded_plugins", []))
    kept = state["messages"][epoch["epoch_start"] :]
    calls = [call for message in kept if isinstance(message, AIMessage) for call in message.tool_calls]
    return {plugin for call in calls if (plugin := mcp.plugin_of(call["name"]))}


async def _prompt_changed(
    state: AgentState, store: BaseStore, user_id: str, thread_id: str, mcp: McpTools, catalog: dict[str, list[str]]
) -> bool:
    """What the epoch's system prompt or tools were built from changed: the name, the pinned skills,
    the prompt texts the user edits or the plugins' tools."""
    if await is_renamed(state, store) or await is_repinned(state, store, user_id, thread_id):
        return True
    if await is_reworded(state):
        return True
    if state.get("plugin_tools", {}) != catalog:
        return True
    return state.get("mcp_tools", []) != mcp.definitions(state.get("loaded_plugins", []))


def _loaded_node(mcp: McpTools) -> Node:
    """Runs after each round of tool calls. A round that asked for plugins' tools (core/plugin_loading.py)
    loads them, so the next call offers them. When the round offered a plugin and the user installed it, a
    new epoch at the same point brings its tools, so the agent uses them now, not from the user's next
    message. Nothing is split or summarized: the prompt and tools change, the messages stay."""

    async def _loaded(state: AgentState, runtime: Runtime[Context], config: RunnableConfig) -> dict:
        calls = _last_calls(state["messages"])
        catalog = mcp.catalog()
        before = state.get("loaded_plugins", [])
        loaded = sorted({*before, *await plugin_loading.requested(calls, catalog, mcp.plugin_of)})
        definitions = mcp.definitions(loaded)
        installed = _offered_plugin(calls) and (
            state.get("plugin_tools", {}) != catalog or state.get("mcp_tools", []) != definitions
        )
        if loaded == before and not installed:
            return {}
        update: dict[str, Any] = {"loaded_plugins": loaded, "mcp_tools": definitions}
        if installed:
            user_id, store = runtime.context.user_id, require_store(runtime.store)
            thread_id = config.get("configurable", {})["thread_id"]
            update |= await reopen(state, store, user_id, thread_id, datetime.now(UTC), catalog)
            update["plugin_tools"] = catalog
        return update

    return _loaded


def _last_calls(messages: Sequence[Any]) -> list[ToolCall]:
    last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    return last.tool_calls if last is not None else []


def _offered_plugin(calls: Sequence[ToolCall]) -> bool:
    return any(call["name"] == "offer_plugin" for call in calls)


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
    """Runs calls to plugins' tools, which the tool node doesn't know: they're looked up when called,
    so a tool that was turned off or whose plugin went away stops working at once."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        if request.tool is not None:
            return await execute(request)
        name = request.tool_call["name"]
        if (tool := mcp.tool(name)) is not None:
            return await execute(request.override(tool=tool))
        if mcp.offered(name):
            return ToolMessage(mcp.unavailable(name), tool_call_id=request.tool_call["id"], name=name, status="error")
        return await execute(request)

    return _wrap


def _agent_node(llm: BaseChatModel, tools: Sequence[BaseTool], images_in_tool_results: bool) -> Node:
    async def _agent(state: AgentState) -> dict:
        epoch = answered(
            without_routed(trimmed(state["messages"], state.get("epoch_start", 0), state.get("trimmed_before", 0)))
        )
        messages = await asyncio.to_thread(hydrate, epoch, images_in_tool_results)
        bound = llm.bind_tools([*tools, *state.get("mcp_tools", [])])
        response = await bound.ainvoke([SystemMessage(state["system_prompt"]), *messages])
        return {
            "messages": [response],
            "usage_anchor": usage_anchor(response, len(state["messages"]) + 1),
            "last_model_call": datetime.now(UTC).isoformat(),
        }

    return _agent
