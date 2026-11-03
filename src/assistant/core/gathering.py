"""Gathering with the worker model and tools that only read: a small graph like a subagent's (core/subagent.py) calls
the tools it's offered for at most MAX_STEPS model calls, then answers with what it found. Home's sections
(core/home/builder.py) and the briefing and reviews (core/proactive/) gather this way, each with its own instructions.

Only the tools offered run, so gathering never changes anything and never waits for an approval: plugins' read-only
tools, looked up live (core/graph.py::mcp_calls), and the assistant's own tools it's built with (reading mail). A
call refused as too large is made again with the tool results left out (core/conversation/oversized.py)."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.types import Send

from assistant.core.context import Context
from assistant.core.conversation.oversized import within_size
from assistant.core.graph import McpTools, Node, each_tool_call, mcp_calls
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.storage import Storage
from assistant.core.usage.meter import TokenMeter

# Model calls to gather with; the calls of the last one don't run, so it answers.
MAX_STEPS = 6
LIMIT_REACHED = "[not run: the step limit was reached. Answer now with what you found.]"
NOTHING_FOUND = "Nothing was found."

_AGENT, _TOOLS = "gather", "gather_tools"


class _GatherState(MessagesState):
    system: str
    # The tools offered: plugins' read-only ones and the assistant's own it was built with.
    tools: list[dict[str, Any]]
    steps: int
    # Before which tool results are sent as stubs: the end, once a call was refused as too large.
    trimmed_before: int


_Graph = CompiledStateGraph[_GatherState, Context, _GatherState, _GatherState]


class Gatherer:
    def __init__(self, graph: _Graph) -> None:
        self._graph = graph

    async def gather(self, context: Context, system: str, task: str, tools: list[dict[str, Any]]) -> str:
        """What it found, or NOTHING_FOUND. Raises what the model calls raise."""
        start = _GatherState(messages=[HumanMessage(task)], system=system, tools=tools, steps=0, trimmed_before=0)
        state = await self._graph.ainvoke(start, {"recursion_limit": 2 * MAX_STEPS + 5}, context=context)
        return _answer(state["messages"])


def build_gatherer(
    storage: Storage, choice: ModelChoice, mcp: McpTools, meter: TokenMeter, own: Sequence[BaseTool] = ()
) -> Gatherer:
    """`own`: the assistant's tools it may run when they're offered, which get the Store and the run's context."""
    llm = metered(build_llm(choice, choice.worker_model), meter)
    builder = StateGraph(_GatherState, context_schema=Context)
    builder.add_node(_AGENT, _agent_node(llm))
    builder.add_node(_TOOLS, ToolNode(list(own), awrap_tool_call=_limited(_offered(mcp_calls(mcp)))))
    builder.add_edge(START, _AGENT)
    builder.add_conditional_edges(_AGENT, _until_limit(each_tool_call(_TOOLS)), [_TOOLS, END])
    builder.add_edge(_TOOLS, _AGENT)
    return Gatherer(builder.compile(store=storage.store))


def _answer(messages: Sequence[BaseMessage]) -> str:
    last = messages[-1] if messages else None
    return (last.text if isinstance(last, AIMessage) else "") or NOTHING_FOUND


def _agent_node(llm: BaseChatModel) -> Node:
    async def _agent(state: _GatherState) -> dict:
        bound = llm.bind_tools(state["tools"])

        async def _call(messages: list[BaseMessage]) -> BaseMessage:
            return await bound.ainvoke([SystemMessage(state["system"]), *messages])

        response, before = await within_size(_call, state["messages"], state["trimmed_before"])
        return {"messages": [response], "steps": state["steps"] + 1, "trimmed_before": before}

    return _agent


def _until_limit(route: Callable[[Any], str | list[Send]]) -> Callable[[_GatherState], str | list[Send]]:
    def _route(state: _GatherState) -> str | list[Send]:
        return END if state["steps"] > MAX_STEPS else route(state)

    return _route


def _limited(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        if request.state["steps"] >= MAX_STEPS:
            return _refused(request, LIMIT_REACHED)
        return await execute_call(request, execute)

    return _wrap


def _offered(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    """Only the tools offered run: a model may call any name."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        name = request.tool_call["name"]
        if name not in {d["function"]["name"] for d in request.state["tools"]}:
            return _refused(request, f"{name} isn't available here: only the read-only tools offered are.")
        return await execute_call(request, execute)

    return _wrap


def _refused(request: ToolCallRequest, text: str) -> ToolMessage:
    call = request.tool_call
    return ToolMessage(text, tool_call_id=call["id"], name=call["name"], status="error")
