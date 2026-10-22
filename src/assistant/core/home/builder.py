"""Builds one Home section: the worker model reads the plugins' tools the section may use, then its findings are
put in the section's format (model.py).

Two steps, so every provider can do it: a small graph like a subagent's (core/subagent.py) gathers with the
tools and says what it found, then the structured model (core/llm/build_structured) writes that as items, which
pydantic validates. Only read-only tools are offered, and only those run, so building Home never changes
anything and never waits for an approval."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest
from langgraph.types import Send

from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL, Context
from assistant.core.conversation import prompts
from assistant.core.graph import McpTools, Node, each_tool_call, mcp_calls
from assistant.core.home.model import HomeSection, SectionContent
from assistant.core.llm import build_llm, build_structured, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.storage import Storage
from assistant.core.usage.meter import TokenMeter

# Model calls to gather a section with; the calls of the last one don't run, so it answers.
MAX_STEPS = 6
LIMIT_REACHED = "[not run: the step limit was reached. Answer now with what you found.]"
NOTHING_FOUND = "Nothing was found."

_AGENT, _TOOLS = "home", "home_tools"


class _GatherState(MessagesState):
    # The read-only tools of the section's plugins.
    tools: list[dict[str, Any]]
    steps: int


_Gather = CompiledStateGraph[_GatherState, Context, _GatherState, _GatherState]


class SectionBuilder:
    def __init__(self, gather: _Gather, structured: Runnable[list[BaseMessage], Any]) -> None:
        self._gather = gather
        self._structured = structured

    async def build(
        self, user_id: str, section: HomeSection, tools: list[dict[str, Any]], now: datetime
    ) -> SectionContent:
        """Raises what the model calls raise, and a validation error for an answer that doesn't fit the format."""
        task = _task(section, now)
        start = _GatherState(messages=[HumanMessage(task)], tools=tools, steps=0)
        state = await self._gather.ainvoke(
            start, {"recursion_limit": 2 * MAX_STEPS + 5}, context=Context(user_id, UNATTENDED_CHANNEL)
        )
        found = HumanMessage(f"{task}\n\nWhat was found:\n{_answer(state['messages'])}")
        content = await self._structured.ainvoke([SystemMessage(prompts.load("home_format")), found])
        return SectionContent.model_validate(content)


def build_section_builder(storage: Storage, choice: ModelChoice, mcp: McpTools) -> SectionBuilder:
    meter = TokenMeter(storage.usage, "home")
    llm = metered(build_llm(choice, choice.worker_model), meter)
    builder = StateGraph(_GatherState, context_schema=Context)
    builder.add_node(_AGENT, _agent_node(llm))
    builder.add_node(_TOOLS, ToolNode([], awrap_tool_call=_limited(_offered(mcp_calls(mcp)))))
    builder.add_edge(START, _AGENT)
    builder.add_conditional_edges(_AGENT, _until_limit(each_tool_call(_TOOLS)), [_TOOLS, END])
    builder.add_edge(_TOOLS, _AGENT)
    return SectionBuilder(builder.compile(), build_structured(choice, choice.worker_model, SectionContent, meter))


def _task(section: HomeSection, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return f"Now: {local:%a %Y-%m-%d %H:%M %Z}.\nSection: {section.title}\n\n{section.prompt}"


def _answer(messages: Sequence[BaseMessage]) -> str:
    last = messages[-1] if messages else None
    return (last.text if isinstance(last, AIMessage) else "") or NOTHING_FOUND


def _agent_node(llm: BaseChatModel) -> Node:
    async def _agent(state: _GatherState) -> dict:
        bound = llm.bind_tools(state["tools"])
        response = await bound.ainvoke([SystemMessage(prompts.load("home")), *state["messages"]])
        return {"messages": [response], "steps": state["steps"] + 1}

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
            return _refused(request, f"{name} isn't available here: only the section's read-only tools are.")
        return await execute_call(request, execute)

    return _wrap


def _refused(request: ToolCallRequest, text: str) -> ToolMessage:
    call = request.tool_call
    return ToolMessage(text, tool_call_id=call["id"], name=call["name"], status="error")
