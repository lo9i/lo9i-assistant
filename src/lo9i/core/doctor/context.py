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

from lo9i.core.config import settings
from lo9i.core.conversation import prompt_edits
from lo9i.core.conversation.prompt import PromptPart, PromptSection, prompt_sections
from lo9i.core.doctor.model import ContextItem, ContextPart, StartingContext
from lo9i.core.i18n import translatable
from lo9i.core.identity import load_name
from lo9i.core.tools.registry import offered_tools
from lo9i.core.usage.tokens import estimate_text

# A starting context past this share of the window alerts: little is left for the conversation itself.
ALERT_SHARE = 0.3
CORE_TOOLS = translatable("Core tool definitions")
PLUGIN_TOOLS = translatable("Plugin tool definitions")

# Kept in English, which names a part across days; shown in the language chosen (changes.py::named).
_LABELS: dict[PromptPart, str] = {
    "persona": translatable("Persona"),
    "name": translatable("Instructions"),
    "operating": translatable("Instructions"),
    "channels": translatable("Channels"),
    "skills": translatable("Skills"),
    "plugin_tools": translatable("Plugins' tools listed"),
    "subagents": translatable("Subagents"),
    "pinned": translatable("Pinned skills"),
    "accounts": translatable("Accounts"),
    "plugins": translatable("Plugins to offer"),
    "profile": translatable("Profile"),
    "facts": translatable("Saved facts"),
    "recent": translatable("Recent conversations"),
    "summary": translatable("Conversation so far"),
}


class PluginTools(Protocol):
    """The tools plugins bring (core/plugin_tools.py)."""

    def catalog(self) -> dict[str, list[str]]: ...

    def definitions(self, loaded: Collection[str]) -> list[dict[str, Any]]: ...


async def starting_context(
    store: BaseStore, user_id: str, plugins: PluginTools, window: int, itemized: bool = False
) -> StartingContext:
    """`window`: the model's context window (core/llm/windows.py). `itemized`: with what each part lists."""
    core = [convert_to_openai_tool(t) for t in offered_tools(settings.toolsets)]
    measured = [
        *(_section(section) for section in await _prompt(store, user_id, plugins)),
        _definitions(CORE_TOOLS, core),
        _definitions(PLUGIN_TOOLS, plugins.definitions(())),
    ]
    parts = [_framed(part) if itemized else part.model_copy(update={"items": []}) for part in _merged(measured)]
    tokens = sum(p.tokens for p in parts)
    return StartingContext(tokens=tokens, window=window, parts=parts, too_large=tokens > window * ALERT_SHARE)


async def _prompt(store: BaseStore, user_id: str, plugins: PluginTools) -> list[PromptSection]:
    """As a new conversation's first epoch builds it: nothing summarized or pinned yet."""
    texts = await prompt_edits.current()
    return await prompt_sections(store, user_id, await load_name(store), "", (), texts, plugins.catalog())


def _section(section: PromptSection) -> ContextPart:
    items = [ContextItem(name=i.name, tokens=estimate_text(i.text), detail=i.detail) for i in section.items]
    return ContextPart(name=_LABELS[section.part], tokens=estimate_text(section.text), items=items)


def _definitions(name: str, definitions: list[dict[str, Any]]) -> ContextPart:
    items = [
        ContextItem(name=d["function"]["name"], tokens=_tokens([d]), detail=_first_line(d["function"]))
        for d in definitions
    ]
    return ContextPart(name=name, tokens=_tokens(definitions), items=items)


def _first_line(function: dict[str, Any]) -> str:
    return str(function.get("description", "")).strip().split("\n", 1)[0]


def _merged(parts: list[ContextPart]) -> list[ContextPart]:
    """Parts of the same name as one (the assistant's name with the operating instructions), in their order."""
    merged: dict[str, ContextPart] = {}
    for part in parts:
        if (before := merged.get(part.name)) is None:
            merged[part.name] = part
        else:
            merged[part.name] = before.model_copy(
                update={"tokens": before.tokens + part.tokens, "items": [*before.items, *part.items]}
            )
    return list(merged.values())


def _framed(part: ContextPart) -> ContextPart:
    """Its items largest first, and the text around them, what the part takes beyond them, as one more."""
    items = sorted(part.items, key=lambda i: i.tokens, reverse=True)
    rest = part.tokens - sum(i.tokens for i in items)
    if rest > 0 and items:
        items.append(ContextItem(name="", tokens=rest, frame=True))
    return part.model_copy(update={"items": sorted(items, key=lambda i: i.tokens, reverse=True)})


def _tokens(definitions: list[dict[str, Any]]) -> int:
    return estimate_text(json.dumps(definitions)) if definitions else 0
