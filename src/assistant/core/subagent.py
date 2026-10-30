"""Subagents: a task the main agent hands off with `delegate`, worked on with a fresh context and the
worker model, so the tool output it reads never reaches the main conversation; only its answer does. It gets the
read-only tools of the plugins the conversation loaded (core/plugin_loading.py). A named subagent a plugin brings
(core/mcp/subagents.py) works with its own instructions after the subagent prompt, on the model it names, with
only the tools it names among those, and the read-only tools of the plugins it names too; its graph is built the
first time it's handed a task, and again when its plugin changes it.

A subagent's graph runs inside the delegate call. It shares the run's checkpointer under that call's
namespace, so an approval inside it pauses the main run and the answer resumes it where it stopped. Its
tool calls stream live inside the delegate call, and are kept with the call's result for history
(core/subagent_steps.py). A call refused as too large is made again with its tool results and files left out
(core/conversation/oversized.py); refused again, the task ends with an answer saying so."""

import asyncio
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import replace
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
from assistant.core.conversation.oversized import within_size
from assistant.core.events import ToolFinished, ToolStarted
from assistant.core.graph import McpTools, Node, each_tool_call, mcp_calls
from assistant.core.i18n import said
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.errors import too_large
from assistant.core.llm.providers import IMAGES_IN_TOOL_RESULTS
from assistant.core.mcp import subagents as named
from assistant.core.mcp.sanitize import MCP_PREFIX
from assistant.core.mcp.subagents import NamedSubagent, UnknownSubagentError
from assistant.core.storage import Storage
from assistant.core.subagent_steps import SubagentAnswer, SubagentStep
from assistant.core.tools.registry import subagent_tools
from assistant.core.usage.meter import TokenMeter

# The result of a tool call made after the subagent's limits ran out.
LIMIT_REACHED = "[not run: this task's step limit was reached. Answer now with what you found.]"
NO_ANSWER = "The subagent stopped at its step limit without an answer."
TOO_LARGE = (
    "The subagent stopped: the model refused its request as too large, even with its tool results and files left "
    "out. Split the task into smaller ones, or do it yourself."
)

# Node names differ from the main graph's, so the subagent's text never streams as the reply
# (core/stream_events.py reads the "agent" node's).
_AGENT, _TOOLS = "subagent", "subagent_tools"


class SubagentState(MessagesState):
    mcp_tools: list[dict[str, Any]]
    # Model calls so far. There's no time limit of its own: every tool call has one, so steps bound it.
    steps: int
    # The delegate call this subagent works for, named by its tool events.
    call_id: str
    # Before which tool results and files are sent as stubs: the end, once a call was refused as too large.
    trimmed_before: int


SubagentGraph = CompiledStateGraph[SubagentState, Context, SubagentState, SubagentState]


class SubagentRunner(Subagents):
    """Runs delegated tasks: the general subagent's on one graph, each named subagent's on its own."""

    def __init__(self, storage: Storage, choice: ModelChoice, mcp: McpTools) -> None:
        self._storage = storage
        self._choice = choice
        self._mcp = mcp
        self._graph = _compiled(
            _llm(storage, choice, choice.worker_model), subagent_tools(settings.toolsets), choice, mcp
        )
        # Each named subagent's graph, with what it was built from.
        self._named: dict[str, tuple[NamedSubagent, SubagentGraph]] = {}

    async def named(self) -> list[NamedSubagent]:
        return await named.installed(self._storage.store)

    async def run(
        self, task: str, context: Context, call_id: str, plugins: Collection[str], agent: str = ""
    ) -> SubagentAnswer:
        """Raises UnknownSubagentError for an `agent` no installed plugin brings."""
        graph = self._graph
        if agent:
            subagent = await self._find(agent)
            graph, plugins = self._graph_of(subagent), [*plugins, *subagent.plugins]
        mcp_tools = self._read_only(plugins)
        start = SubagentState(
            messages=[HumanMessage(task)], mcp_tools=mcp_tools, steps=0, call_id=call_id, trimmed_before=0
        )
        state = await graph.ainvoke(
            start,
            {"recursion_limit": 2 * settings.subagent_max_steps + 5},
            context=replace(context, subagents=None),
        )
        return SubagentAnswer(answer(state["messages"]), steps(state["messages"]))

    async def _find(self, agent: str) -> NamedSubagent:
        found = {s.name: s for s in await self.named()}
        if agent not in found:
            listed = ", ".join(found) or "none"
            raise UnknownSubagentError(
                said("No subagent named {agent}. The named ones: {listed}.", agent=agent, listed=listed)
            )
        return found[agent]

    def _graph_of(self, subagent: NamedSubagent) -> SubagentGraph:
        kept = self._named.get(subagent.name)
        if kept is not None and kept[0] == subagent:
            return kept[1]
        choice = self._choice
        model = {"main": choice.model, "worker": choice.worker_model}.get(subagent.model, subagent.model)
        tools = [t for t in subagent_tools(settings.toolsets) if not subagent.tools or t.name in subagent.tools]
        prompt = f"{prompts.load('subagent')}\n\n{subagent.prompt}"
        graph = _compiled(_llm(self._storage, choice, model), tools, choice, self._mcp, prompt)
        self._named[subagent.name] = (subagent, graph)
        return graph

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
    return SubagentRunner(storage, choice, mcp)


def _llm(storage: Storage, choice: ModelChoice, model: str) -> BaseChatModel:
    return metered(build_llm(choice, model), TokenMeter(storage.usage, "subagent"))


def _compiled(
    llm: BaseChatModel, tools: Sequence[BaseTool], choice: ModelChoice, mcp: McpTools, prompt: str = ""
) -> SubagentGraph:
    """A subagent's graph; `prompt` is its system prompt, the subagent prompt when empty."""
    builder = StateGraph(SubagentState, context_schema=Context)
    images = choice.provider in IMAGES_IN_TOOL_RESULTS
    builder.add_node(_AGENT, _agent_node(llm, tools, images, prompt))
    builder.add_node(_TOOLS, ToolNode(tools, awrap_tool_call=_reported(_limited(_offered_mcp(mcp_calls(mcp))))))
    builder.add_edge(START, _AGENT)
    builder.add_conditional_edges(_AGENT, _until_limit(each_tool_call(_TOOLS)), [_TOOLS, END])
    builder.add_edge(_TOOLS, _AGENT)
    return builder.compile()


def _agent_node(llm: BaseChatModel, tools: Sequence[BaseTool], images_in_tool_results: bool, prompt: str) -> Node:
    async def _agent(state: SubagentState) -> dict:
        bound = llm.bind_tools([*tools, *state["mcp_tools"]])

        async def _call(messages: list[BaseMessage]) -> BaseMessage:
            hydrated = await asyncio.to_thread(hydrate, messages, images_in_tool_results)
            system = prompt or prompts.load("subagent")
            return await bound.ainvoke([SystemMessage(system), *hydrated])

        response, before = await _within_size(_call, state)
        if isinstance(response, AIMessage):
            _report_calls(response, state["call_id"])
        return {"messages": [response], "steps": state["steps"] + 1, "trimmed_before": before}

    return _agent


async def _within_size(
    call: Callable[[list[BaseMessage]], Awaitable[BaseMessage]], state: SubagentState
) -> tuple[BaseMessage, int]:
    """Still too large with every result left out, the answer says so, which ends the task."""
    try:
        return await within_size(call, state["messages"], state.get("trimmed_before", 0))
    except Exception as e:
        if not too_large(e):
            raise
        return AIMessage(TOO_LARGE), len(state["messages"])


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
