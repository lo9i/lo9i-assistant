import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
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
    rename,
    usage_anchor,
)
from assistant.core.llm import build_llm
from assistant.core.storage import Storage
from assistant.core.tools import tools_for

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


Graph = CompiledStateGraph[AgentState, Context, AgentState, AgentState]


def build_graph(storage: Storage, model: str, digester: Digester) -> Graph:
    tools = tools_for(settings.toolsets)
    builder = StateGraph(AgentState, context_schema=Context)
    builder.add_node("epoch", _epoch_node(digester))
    builder.add_node("agent", _agent_node(build_llm(model).bind_tools(tools)))
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "epoch")
    builder.add_edge("epoch", "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=storage.checkpointer, store=storage.store)


def _epoch_node(digester: Digester) -> Node:
    """Runs once per user message: opens the first epoch, or starts a new one when needed."""

    async def _epoch(state: AgentState, runtime: Runtime[Context]) -> dict:
        now = datetime.now(UTC)
        user_id, store = runtime.context.user_id, require_store(runtime.store)
        update: dict = {}
        if not state.get("system_prompt"):
            update = await open_epoch(store, user_id, now)
        elif is_idle(state, now) or is_too_large(state):
            update = await compact(state, store, user_id, digester, now)
        elif await is_renamed(state, store):
            update = await rename(state, store, user_id, now)
        return {**update, "last_activity": now.isoformat()}

    return _epoch


def _agent_node(llm: Runnable[LanguageModelInput, BaseMessage]) -> Node:
    async def _agent(state: AgentState) -> dict:
        epoch = state["messages"][state.get("epoch_start", 0) :]
        messages = await asyncio.to_thread(hydrate, epoch)
        response = await llm.ainvoke([SystemMessage(state["system_prompt"]), *messages])
        return {"messages": [response], "usage_anchor": usage_anchor(response, len(state["messages"]) + 1)}

    return _agent
