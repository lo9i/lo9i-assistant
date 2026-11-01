"""Subagents: a task the main agent hands off with `delegate`, worked on with a fresh context and the
worker model, so the tool output it reads never reaches the main conversation; only its answer does. It gets the
read-only tools of the plugins the conversation loaded (core/plugin_loading.py) and of those the delegate call names,
which load for it alone, so the conversation's tool list (and its prompt cache) stays as it is. A named subagent a
plugin brings (core/mcp/subagents.py) works with its own instructions after the subagent prompt, on the model it
names, with only the tools it names among those, and the read-only tools of the plugins it names too; its graph is
built the first time it's handed a task, and again when its plugin changes it.

A subagent's graph runs inside the delegate call. It shares the run's checkpointer under that call's
namespace, so an approval inside it pauses the main run and the answer resumes it where it stopped. Its
tool calls stream live inside the delegate call, and are kept with the call's result for history
(core/subagent_steps.py). A call refused as too large is made again with its tool results and files left out
(core/conversation/oversized.py); refused again, the task ends with an answer saying so.

A subagent sent off in the background (core/background_subagents/) runs on a graph of its own kind: its
checkpoints go under a thread of its own, so an approval pauses only it, and it has no step limit."""

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
# One in the background has no step limit.
NO_BACKGROUND_ANSWER = "The subagent ended without an answer."
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
        llm, tools = _llm(storage, choice, choice.worker_model), subagent_tools(settings.toolsets)
        self._graph = _compiled(llm, tools, choice, mcp)
        self._background = _compiled(llm, tools, choice, mcp, saved=storage)
        # Each named subagent's graphs (the one run inside a delegate call, the one in the background), with what
        # they were built from.
        self._named: dict[tuple[str, bool], tuple[NamedSubagent, SubagentGraph]] = {}

    async def named(self) -> list[NamedSubagent]:
        return await named.installed(self._storage.store)

    async def run(
        self, task: str, context: Context, call_id: str, plugins: Collection[str], agent: str = ""
    ) -> SubagentAnswer:
        """Raises UnknownSubagentError for an `agent` no installed plugin brings."""
        graph, start = await self._prepared(task, call_id, plugins, agent, background=False)
        state = await graph.ainvoke(
            start,
            {"recursion_limit": 2 * settings.subagent_max_steps + 5},
            context=replace(context, subagents=None, background=None),
        )
        return SubagentAnswer(answer(state["messages"]), steps(state["messages"]))

    def readable_plugins(self) -> set[str]:
        return {plugin for d in self._mcp.read_only_definitions() if (plugin := self._mcp.plugin_of(_name(d)))}

    async def background_start(self, task: str, plugins: Collection[str], agent: str = "") -> SubagentState:
        """Where a subagent sent off in the background starts, its tools' events naming no call. Raises
        UnknownSubagentError for an `agent` no installed plugin brings."""
        return (await self._prepared(task, "", plugins, agent, background=True))[1]

    async def background_graph(self, agent: str = "") -> SubagentGraph:
        """The graph a subagent sent off in the background runs on: it saves its checkpoints, and has no step limit.
        Raises UnknownSubagentError when `agent`'s plugin went away."""
        return self._background if not agent else self._graph_of(await self._find(agent), background=True)

    async def _prepared(
        self, task: str, call_id: str, plugins: Collection[str], agent: str, background: bool
    ) -> tuple[SubagentGraph, SubagentState]:
        graph = self._background if background else self._graph
        if agent:
            subagent = await self._find(agent)
            graph, plugins = self._graph_of(subagent, background), [*plugins, *subagent.plugins]
        start = SubagentState(
            messages=[HumanMessage(task)],
            mcp_tools=self._read_only(plugins),
            steps=0,
            call_id=call_id,
            trimmed_before=0,
        )
        return graph, start

    async def _find(self, agent: str) -> NamedSubagent:
        found = {s.name: s for s in await self.named()}
        if agent not in found:
            listed = ", ".join(found) or "none"
            raise UnknownSubagentError(
                said("No subagent named {agent}. The named ones: {listed}.", agent=agent, listed=listed)
            )
        return found[agent]

    def _graph_of(self, subagent: NamedSubagent, background: bool) -> SubagentGraph:
        kept = self._named.get((subagent.name, background))
        if kept is not None and kept[0] == subagent:
            return kept[1]
        choice = self._choice
        model = {"main": choice.model, "worker": choice.worker_model}.get(subagent.model, subagent.model)
        tools = [t for t in subagent_tools(settings.toolsets) if not subagent.tools or t.name in subagent.tools]
        prompt = f"{prompts.load('subagent')}\n\n{subagent.prompt}"
        saved = self._storage if background else None
        graph = _compiled(_llm(self._storage, choice, model), tools, choice, self._mcp, prompt, saved)
        self._named[(subagent.name, background)] = (subagent, graph)
        return graph

    def _read_only(self, plugins: Collection[str]) -> list[dict[str, Any]]:
        """The read-only tools of these plugins: the others' would fill every request of the task."""
        definitions = self._mcp.read_only_definitions()
        return [d for d in definitions if self._mcp.plugin_of(_name(d)) in plugins]


def _name(definition: dict[str, Any]) -> str:
    return definition["function"]["name"]


def answer(messages: Sequence[Any], missing: str = NO_ANSWER) -> str:
    """Its last reply; `missing` when it ended without one."""
    last = messages[-1] if messages else None
    return (last.text if isinstance(last, AIMessage) else "") or missing


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
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    choice: ModelChoice,
    mcp: McpTools,
    prompt: str = "",
    saved: Storage | None = None,
) -> SubagentGraph:
    """A subagent's graph; `prompt` is its system prompt, the subagent prompt when empty. Run inside a delegate call
    it shares the run's checkpointer and store, and stops at the step limit; `saved`, for one sent off in the
    background, has its own and no limit."""
    builder = StateGraph(SubagentState, context_schema=Context)
    images = choice.provider in IMAGES_IN_TOOL_RESULTS
    builder.add_node(_AGENT, _agent_node(llm, tools, images, prompt))
    calls = _offered_mcp(mcp_calls(mcp))
    route = each_tool_call(_TOOLS)
    if saved is None:
        calls, route = _limited(calls), _until_limit(route)
    builder.add_node(_TOOLS, ToolNode(tools, awrap_tool_call=_reported(calls)))
    builder.add_edge(START, _AGENT)
    builder.add_conditional_edges(_AGENT, route, [_TOOLS, END])
    builder.add_edge(_TOOLS, _AGENT)
    if saved is None:
        return builder.compile()
    return builder.compile(checkpointer=saved.checkpointer, store=saved.store)


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
