"""Subagents: a task the main agent hands off with `delegate`, worked on with a fresh context and the
worker model, so the tool output it reads never reaches the main conversation; only its answer does. It gets the
read-only tools of the plugins the conversation loaded (core/plugin_loading.py).

A subagent's graph runs inside the delegate call. It shares the run's checkpointer under that call's
namespace, so an approval inside it pauses the main run and the answer resumes it where it stopped. Its
tool calls stream live inside the delegate call, and are kept with the call's result for history
(core/subagent_steps.py)."""

import asyncio
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import replace
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.types import Send

from assistant.core.attachments import hydrate
from assistant.core.config import settings
from assistant.core.context import Context, Subagents
from assistant.core.conversation import prompts
from assistant.core.events import ToolFinished, ToolStarted
from assistant.core.graph import McpTools, Node, each_tool_call, mcp_calls
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.providers import IMAGES_IN_TOOL_RESULTS
from assistant.core.mcp.sanitize import MCP_PREFIX
from assistant.core.storage import Storage
from assistant.core.subagent_steps import SubagentAnswer, SubagentStep
from assistant.core.tools.registry import subagent_tools
from assistant.core.usage.meter import TokenMeter

# The result of a tool call made after the subagent's limits ran out.
LIMIT_REACHED = "[not run: this task's step limit was reached. Answer now with what you found.]"
NO_ANSWER = "The subagent stopped at its step limit without an answer."

# Node names differ from the main graph's, so the subagent's text never streams as the reply
# (core/stream_events.py reads the "agent" node's).
_AGENT, _TOOLS = "subagent", "subagent_tools"


class SubagentState(MessagesState):
    mcp_tools: list[dict[str, Any]]
    # Model calls so far. There's no time limit of its own: every tool call has one, so steps bound it.
    steps: int
    # The delegate call this subagent works for, named by its tool events.
    call_id: str


SubagentGraph = CompiledStateGraph[SubagentState, Context, SubagentState, SubagentState]


class SubagentRunner(Subagents):
    """Runs delegated tasks on one compiled subagent graph."""

    def __init__(self, graph: SubagentGraph, mcp: McpTools) -> None:
        self._graph = graph
        self._mcp = mcp

    async def run(self, task: str, context: Context, call_id: str, plugins: Collection[str]) -> SubagentAnswer:
        mcp_tools = self._read_only(plugins)
        start = SubagentState(messages=[HumanMessage(task)], mcp_tools=mcp_tools, steps=0, call_id=call_id)
        state = await self._graph.ainvoke(
            start,
            {"recursion_limit": 2 * settings.subagent_max_steps + 5},
            context=replace(context, subagents=None),
        )
        return SubagentAnswer(answer(state["messages"]), steps(state["messages"]))

    def _read_only(self, plugins: Collection[str]) -> list[dict[str, Any]]:
        """The read-only tools of these plugins: the others' would fill every request of the task."""
        definitions = self._mcp.read_only_definitions()
        return [d for d in definitions if self._mcp.plugin_of(d["function"]["name"]) in plugins]


def answer(messages: Sequence[Any]) -> str:
    last = messages[-1] if messages else None
    return (last.text if isinstance(last, AIMessage) else "") or NO_ANSWER


def steps(messages: Sequence[Any]) -> list[SubagentStep]:
    """Its tool calls that ran, each with its result. The last step's calls end the task unrun."""
    results = {m.tool_call_id: m.text for m in messages if isinstance(m, ToolMessage)}
    calls = [call for m in messages if isinstance(m, AIMessage) for call in m.tool_calls]
    return [SubagentStep(c["name"], c["args"], results[c["id"]]) for c in calls if c["id"] in results]


def build_subagents(storage: Storage, choice: ModelChoice, mcp: McpTools) -> SubagentRunner:
    llm = metered(build_llm(choice, choice.worker_model), TokenMeter(storage.usage, "subagent"))
    tools = subagent_tools(settings.toolsets)
    builder = StateGraph(SubagentState, context_schema=Context)
    builder.add_node(_AGENT, _agent_node(llm, tools, choice.provider in IMAGES_IN_TOOL_RESULTS))
    builder.add_node(_TOOLS, ToolNode(tools, awrap_tool_call=_reported(_limited(_offered_mcp(mcp_calls(mcp))))))
    builder.add_edge(START, _AGENT)
    builder.add_conditional_edges(_AGENT, _until_limit(each_tool_call(_TOOLS)), [_TOOLS, END])
    builder.add_edge(_TOOLS, _AGENT)
    return SubagentRunner(builder.compile(), mcp)


def _agent_node(llm: BaseChatModel, tools: Sequence[BaseTool], images_in_tool_results: bool) -> Node:
    async def _agent(state: SubagentState) -> dict:
        messages = await asyncio.to_thread(hydrate, state["messages"], images_in_tool_results)
        bound = llm.bind_tools([*tools, *state["mcp_tools"]])
        response = await bound.ainvoke([SystemMessage(prompts.load("subagent")), *messages])
        if isinstance(response, AIMessage):
            _report_calls(response, state["call_id"])
        return {"messages": [response], "steps": state["steps"] + 1}

    return _agent


def _report_calls(response: AIMessage, call_id: str) -> None:
    write = get_stream_writer()
    for call in response.tool_calls:
        write(ToolStarted(call["name"], call["args"], id=call["id"] or "", within=call_id))


def _reported(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    """Streams each result to the apps as the delegate call's progress."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        result = await execute_call(request, execute)
        if isinstance(result, ToolMessage):
            get_stream_writer()(ToolFinished(result.name or "", result.text, within=request.state["call_id"]))
        return result

    return _wrap


def _until_limit(route: Callable[[Any], str | list[Send]]) -> Callable[[SubagentState], str | list[Send]]:
    """The reply after the last step ends the task, even if it calls tools."""

    def _route(state: SubagentState) -> str | list[Send]:
        return END if state["steps"] > settings.subagent_max_steps else route(state)

    return _route


def _limited(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    """Calls of the last step don't run, so the next reply is the answer."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        if request.state["steps"] >= settings.subagent_max_steps:
            return _refused(request, LIMIT_REACHED)
        return await execute_call(request, execute)

    return _wrap


def _offered_mcp(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    """Only the MCP tools the subagent was offered run: the read-only ones."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        name = request.tool_call["name"]
        offered = {d["function"]["name"] for d in request.state["mcp_tools"]}
        if name.startswith(MCP_PREFIX) and name not in offered:
            return _refused(request, f"{name} isn't available to a subagent: it can change things.")
        return await execute_call(request, execute)

    return _wrap


def _refused(request: ToolCallRequest, text: str) -> ToolMessage:
    call = request.tool_call
    return ToolMessage(text, tool_call_id=call["id"], name=call["name"], status="error")
