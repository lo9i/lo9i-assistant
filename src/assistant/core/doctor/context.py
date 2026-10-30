"""The context a new conversation starts with: its system prompt, built as an epoch builds it (core/conversation/
prompt.py), part by part, and the tool definitions every request carries (the core tools, and what plugins add
before any is loaded), counted as the daemon estimates tokens (core/usage/tokens.py). It's measured against the
model's context window, as the chat's context bar measures a conversation (core/llm/windows.py; EPOCH_MAX_TOKENS
when the provider doesn't say)."""

import json
from collections.abc import Collection
from typing import Any, Protocol

from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation import prompt_edits
from assistant.core.conversation.prompt import PromptPart, prompt_parts
from assistant.core.doctor.model import ContextPart, StartingContext
from assistant.core.identity import load_name
from assistant.core.tools.registry import offered_tools
from assistant.core.usage.tokens import estimate_text

# A starting context past this share of the window alerts: little is left for the conversation itself.
ALERT_SHARE = 0.3
CORE_TOOLS = "Core tool definitions"
PLUGIN_TOOLS = "Plugin tool definitions"

_LABELS: dict[PromptPart, str] = {
    "persona": "Persona",
    "name": "Instructions",
    "operating": "Instructions",
    "channels": "Channels",
    "skills": "Skills",
    "plugin_tools": "Plugins' tools listed",
    "subagents": "Subagents",
    "pinned": "Pinned skills",
    "accounts": "Accounts",
    "plugins": "Plugins to offer",
    "profile": "Profile",
    "facts": "Saved facts",
    "recent": "Recent conversations",
    "summary": "Conversation so far",
}


class PluginTools(Protocol):
    """The tools plugins bring (core/plugin_tools.py)."""

    def catalog(self) -> dict[str, list[str]]: ...

    def definitions(self, loaded: Collection[str]) -> list[dict[str, Any]]: ...


async def starting_context(store: BaseStore, user_id: str, plugins: PluginTools, window: int) -> StartingContext:
    """`window`: the model's context window (core/llm/windows.py)."""
    sizes: dict[str, int] = {}
    for part, text in await _prompt(store, user_id, plugins):
        sizes[_LABELS[part]] = sizes.get(_LABELS[part], 0) + estimate_text(text)
    sizes[CORE_TOOLS] = _tokens([convert_to_openai_tool(t) for t in offered_tools(settings.toolsets)])
    sizes[PLUGIN_TOOLS] = _tokens(plugins.definitions(()))
    tokens = sum(sizes.values())
    return StartingContext(
        tokens=tokens,
        window=window,
        parts=[ContextPart(name=name, tokens=size) for name, size in sizes.items()],
        too_large=tokens > window * ALERT_SHARE,
    )


async def _prompt(store: BaseStore, user_id: str, plugins: PluginTools) -> list[tuple[PromptPart, str]]:
    """As a new conversation's first epoch builds it: nothing summarized or pinned yet."""
    texts = await prompt_edits.current()
    return await prompt_parts(store, user_id, await load_name(store), "", (), texts, plugins.catalog())


def _tokens(definitions: list[dict[str, Any]]) -> int:
    return estimate_text(json.dumps(definitions)) if definitions else 0
