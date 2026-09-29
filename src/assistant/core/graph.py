from collections.abc import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.context import Context
from assistant.core.llm import build_llm
from assistant.core.memory import Memory
from assistant.core.tools import tools_for
from assistant.core.tools.memory import namespace

_SYSTEM_PROMPT = """You are a personal assistant for a single user.

You run inside a Docker container. The bash tool runs commands there, in the workspace directory.
The user reaches you through several channels (CLI, Telegram, web UI) and one conversation continues across them.

Use the remember tool when the user shares something worth knowing in future conversations, and forget when a saved memory turns out wrong. Changes to memories take effect in the next conversation.

Saved memories about the user:
{memories}"""


class AgentState(MessagesState):
    # Built once on the first turn and reused for the whole conversation, so the
    # prompt prefix stays byte-identical and the prompt cache keeps hitting.
    system_prompt: str


def build_graph(memory: Memory, model: str) -> CompiledStateGraph:
    tools = tools_for(settings.toolsets)
    builder = StateGraph(AgentState, context_schema=Context)
    builder.add_node("agent", _agent_node(build_llm(model).bind_tools(tools)))
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=memory.checkpointer, store=memory.store)


def _agent_node(llm: BaseChatModel) -> Callable[..., Awaitable[dict]]:
    async def _agent(state: AgentState, runtime: Runtime[Context]) -> dict:
        update = {}
        system_prompt = state.get("system_prompt")
        if not system_prompt:
            system_prompt = await _build_system_prompt(runtime.store, runtime.context.user_id)
            update["system_prompt"] = system_prompt
        response = await llm.ainvoke([SystemMessage(system_prompt), *state["messages"]])
        return {**update, "messages": [response]}

    return _agent


async def _build_system_prompt(store: BaseStore, user_id: str) -> str:
    items = await store.asearch(namespace(user_id), limit=200)
    lines = sorted(f"- [{i.key}] {i.value['fact']}" for i in items)
    return _SYSTEM_PROMPT.format(memories="\n".join(lines) or "(none yet)")
