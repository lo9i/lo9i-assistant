"""Builds the system prompt at the start of each epoch.

Order runs from stable to volatile: persona, the assistant's name, operating instructions, channel hints,
skills, the plugins whose tools load on demand, the skills pinned to the conversation, connected accounts,
plugins it can offer, then profile, facts, recent episodes and the running summary. Prompt texts live in
`prompts/`; the persona, operating instructions and channel hints are the user's edits when there are some
(prompt_edits.py).
"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation import prompt_edits, prompts
from assistant.core.integrations.email import accounts
from assistant.core.mcp import servers, subagents
from assistant.core.memory import episodes, facts, profile
from assistant.core.repositories import offers
from assistant.core.skills import store as skills
from assistant.core.skills.instructions import render as render_skill
from assistant.core.skills.store import SkillError

_NAME = prompts.load("name")
_ACCOUNTS = prompts.load("accounts")
_PLUGINS = prompts.load("plugins")
_PINNED = prompts.load("pinned")
_PLUGIN_TOOLS = prompts.load("plugin_tools")

PromptPart = Literal[
    "persona",
    "name",
    "operating",
    "channels",
    "skills",
    "plugin_tools",
    "subagents",
    "pinned",
    "accounts",
    "plugins",
    "profile",
    "facts",
    "recent",
    "summary",
]


async def build_system_prompt(
    store: BaseStore,
    user_id: str,
    name: str,
    conversation_summary: str,
    pinned: Sequence[str] = (),
    texts: Mapping[str, str] | None = None,
    plugin_tools: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """`texts`: the texts the user can edit, by name (prompt_edits.current()); read now when left out.
    `plugin_tools`: each plugin with tools and their names, which a conversation loads when it needs them
    (core/plugin_loading.py)."""
    parts = await prompt_parts(store, user_id, name, conversation_summary, pinned, texts, plugin_tools)
    return "\n\n".join(text for _, text in parts)


async def prompt_parts(
    store: BaseStore,
    user_id: str,
    name: str,
    conversation_summary: str,
    pinned: Sequence[str] = (),
    texts: Mapping[str, str] | None = None,
    plugin_tools: Mapping[str, Sequence[str]] | None = None,
) -> list[tuple[PromptPart, str]]:
    """The system prompt's sections in order, each with the part it is (the doctor measures each one,
    core/doctor/context.py). Parts with nothing to say are left out."""
    texts = await prompt_edits.current() if texts is None else texts
    recent = await episodes.recent(store, user_id, settings.memory_max_episodes)
    parts: list[tuple[PromptPart, str | None]] = [
        ("persona", texts["persona"]),
        ("name", _NAME.format(name=name) if name else None),
        ("operating", texts["operating"]),
        ("channels", f"# Channels\n\n{await _channels_index(store, texts['channels'])}"),
        ("skills", f"# Skills\n\n{await _skills_index()}"),
        ("plugin_tools", _plugin_tools_section(plugin_tools or {})),
        ("subagents", await _subagents_section(store)),
        ("pinned", await _pinned_section(pinned)),
        ("accounts", f"# Accounts\n\n{await _accounts_index(store)}"),
        ("plugins", await _plugins_section(store)),
        ("profile", f"# User profile\n\n{profile.render(await profile.load(store, user_id))}"),
        ("facts", f"# Saved facts\n\n{facts.render(await facts.load(store, user_id, settings.memory_max_facts))}"),
        ("recent", f"# Recent conversations\n\n{episodes.render(recent)}"),
        ("summary", f"# Conversation so far\n\n{conversation_summary}" if conversation_summary else None),
    ]
    return [(part, text) for part, text in parts if text is not None]


async def _channels_index(store: BaseStore, hints: str) -> str:
    """The apps' channels, then the chat channels installed as plugins, each saying how to write there."""
    installed = [s for s in await servers.load_all(store) if s.channel_command and s.enabled]
    return "\n".join([hints, *(f"- {s.name}: {s.channel_style}" for s in installed if s.channel_style)])


async def _skills_index() -> str:
    listed = await asyncio.to_thread(skills.list_skills)
    lines = "\n".join(f"- {s.name}: {s.description}" for s in listed)
    return f"To run a skill, call use_skill with its name and follow the instructions.\n\n{lines or '(none yet)'}"


async def _subagents_section(store: BaseStore) -> str | None:
    """The named subagents plugins bring (core/mcp/subagents.py); no section without any."""
    found = await subagents.installed(store)
    if not found:
        return None
    lines = "\n".join(f"- {s.name}: {s.description}" for s in found)
    return f"# Subagents\n\nNamed subagents, for delegate's `agent` when a task is what one is made for:\n\n{lines}"


def _plugin_tools_section(plugin_tools: Mapping[str, Sequence[str]]) -> str | None:
    """No section when no plugin has tools."""
    lines = "\n".join(f"- {plugin}: {', '.join(tools)}" for plugin, tools in sorted(plugin_tools.items()))
    return f"# Plugin tools\n\n{_PLUGIN_TOOLS}\n\n{lines}" if lines else None


async def _pinned_section(names: Sequence[str]) -> str | None:
    """The pinned skills in full; no section when none is pinned. A pinned skill that was deleted is
    left out. Like memory, a pinned skill edited mid-epoch shows from the next one."""
    parts = [f"## Skill: {skill.name}\n\n{render_skill(skill)}" for skill in await _loaded(names)]
    return f"# Pinned skills\n\n{_PINNED}\n\n" + "\n\n".join(parts) if parts else None


async def _loaded(names: Sequence[str]) -> list[skills.Skill]:
    loaded = []
    for name in names:
        try:
            loaded.append(await asyncio.to_thread(skills.load, name))
        except SkillError:
            continue
    return loaded


async def _plugins_section(store: BaseStore) -> str | None:
    """The plugins the agent can offer; no section when there are none. Like accounts, a plugin
    installed or added to the extras shows from the next epoch."""
    lines = "\n".join(f"- {o.name}: {o.description}" for o in await offers.offerable(store))
    return f"# Plugins you can offer\n\n{_PLUGINS}\n\n{lines}" if lines else None


async def _accounts_index(store: BaseStore) -> str:
    """Account changes show from the next epoch, like memory: the prompt stays the same within one."""
    lines = [
        f"- email: {c.label} <{c.sender}>" + (" (default)" if c.default else "")
        for c in await accounts.list_accounts(store)
    ]
    return f"{_ACCOUNTS}\n\n" + ("\n".join(lines) or "(none connected)")
