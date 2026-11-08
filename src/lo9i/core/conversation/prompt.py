"""Builds the system prompt at the start of each epoch.

Order runs from stable to volatile: persona, the assistant's name, operating instructions, channel hints,
skills, the plugins whose tools load on demand, the skills pinned to the conversation, connected accounts,
plugins it can offer, then profile, the basic facts, the facts the conversation brought up (relevant_facts.py),
recent episodes and the running summary. Prompt texts live in
`prompts/`; the persona, operating instructions and channel hints are the user's edits when there are some
(prompt_edits.py).
"""

import asyncio
import logging
from collections.abc import Mapping, Sequence

from langgraph.store.base import BaseStore

from lo9i.core.config import settings
from lo9i.core.conversation import prompt_edits, prompts
from lo9i.core.conversation.prompt_sections import (
    PromptItem,
    PromptPart,
    PromptSection,
    by_heading,
    headed,
    listed,
)
from lo9i.core.integrations.email import accounts
from lo9i.core.mcp import servers, subagents
from lo9i.core.memory import episodes, facts, profile
from lo9i.core.memory.facts import Fact
from lo9i.core.repositories import offers
from lo9i.core.skills import store as skills
from lo9i.core.skills.instructions import render as render_skill
from lo9i.core.skills.store import SkillError

_NAME = prompts.load("name")
_ACCOUNTS = prompts.load("accounts")
_PLUGINS = prompts.load("plugins")
_PINNED = prompts.load("pinned")
_PLUGIN_TOOLS = prompts.load("plugin_tools")
_FACTS = prompts.load("facts")
_RELEVANT = prompts.load("relevant_facts")

logger = logging.getLogger(__name__)

__all__ = ["PromptItem", "PromptPart", "PromptSection", "build_system_prompt", "prompt_sections"]


async def build_system_prompt(
    store: BaseStore,
    user_id: str,
    name: str,
    conversation_summary: str,
    pinned: Sequence[str] = (),
    texts: Mapping[str, str] | None = None,
    plugin_tools: Mapping[str, Sequence[str]] | None = None,
    relevant: Sequence[Fact] = (),
) -> str:
    """`texts`: the texts the user can edit, by name (prompt_edits.current()); read now when left out.
    `plugin_tools`: each plugin with tools and their names, which a conversation loads when it needs them
    (core/plugin_loading.py). `relevant`: the facts the conversation brought up (relevant_facts.py)."""
    sections = await prompt_sections(store, user_id, name, conversation_summary, pinned, texts, plugin_tools, relevant)
    return "\n\n".join(section.text for section in sections)


async def prompt_sections(
    store: BaseStore,
    user_id: str,
    name: str,
    conversation_summary: str,
    pinned: Sequence[str] = (),
    texts: Mapping[str, str] | None = None,
    plugin_tools: Mapping[str, Sequence[str]] | None = None,
    relevant: Sequence[Fact] = (),
) -> list[PromptSection]:
    """The system prompt's sections in order, each with the part it is and the items it lists (the doctor measures
    each one, core/doctor/context.py). Parts with nothing to say are left out."""
    texts = await prompt_edits.current() if texts is None else texts
    sections: list[PromptSection | None] = [
        by_heading("persona", texts["persona"]),
        _name_section(name),
        by_heading("operating", texts["operating"]),
        await _channels_section(store, texts["channels"]),
        await _skills_section(),
        _plugin_tools_section(plugin_tools or {}),
        await _subagents_section(store),
        await _pinned_section(pinned),
        await _accounts_section(store),
        await _plugins_section(store),
        await _profile_section(store, user_id),
        *await _facts_sections(store, user_id, relevant),
        await _recent_section(store, user_id),
        _summary_section(conversation_summary),
    ]
    return [section for section in sections if section is not None]


def _name_section(name: str) -> PromptSection | None:
    return (
        PromptSection("name", _NAME.format(name=name), (PromptItem(name, _NAME.format(name=name)),)) if name else None
    )


async def _channels_section(store: BaseStore, hints: str) -> PromptSection:
    """The apps' channels, then the chat channels installed as plugins, each saying how to write there."""
    installed = [s for s in await servers.load_all(store) if s.channel_command and s.enabled]
    own = [PromptItem(s.name, f"- {s.name}: {s.channel_style}", s.channel_style) for s in installed if s.channel_style]
    items = [*headed(hints), *own]
    return PromptSection("channels", "# Channels\n\n" + "\n".join([hints, *(i.text for i in own)]), tuple(items))


async def _skills_section() -> PromptSection:
    listed_skills = await asyncio.to_thread(skills.list_skills)
    items = [PromptItem(s.name, f"- {s.name}: {s.description}", s.description) for s in listed_skills]
    head = "# Skills\n\nTo run a skill, call use_skill with its name and follow the instructions.\n\n"
    return listed("skills", head, items, "(none yet)")


async def _subagents_section(store: BaseStore) -> PromptSection | None:
    """The named subagents plugins bring (core/mcp/subagents.py); no section without any."""
    found = await subagents.installed(store)
    if not found:
        return None
    items = [PromptItem(s.name, f"- {s.name}: {s.description}", s.description) for s in found]
    head = "# Subagents\n\nNamed subagents, for delegate's `agent` when a task is what one is made for:\n\n"
    return listed("subagents", head, items, "")


def _plugin_tools_section(plugin_tools: Mapping[str, Sequence[str]]) -> PromptSection | None:
    """No section when no plugin has tools."""
    items = [
        PromptItem(plugin, f"- {plugin}: {', '.join(tools)}", ", ".join(tools))
        for plugin, tools in sorted(plugin_tools.items())
    ]
    return listed("plugin_tools", f"# Plugin tools\n\n{_PLUGIN_TOOLS}\n\n", items, "") if items else None


async def _pinned_section(names: Sequence[str]) -> PromptSection | None:
    """The pinned skills in full; no section when none is pinned. A pinned skill that was deleted is
    left out. Like memory, a pinned skill edited mid-epoch shows from the next one."""
    items = [
        PromptItem(skill.name, f"## Skill: {skill.name}\n\n{render_skill(skill)}", skill.description)
        for skill in await _loaded(names)
    ]
    if not items:
        return None
    text = f"# Pinned skills\n\n{_PINNED}\n\n" + "\n\n".join(i.text for i in items)
    return PromptSection("pinned", text, tuple(items))


async def _loaded(names: Sequence[str]) -> list[skills.Skill]:
    loaded = []
    for name in names:
        try:
            loaded.append(await asyncio.to_thread(skills.load, name))
        except SkillError:
            continue
    return loaded


async def _plugins_section(store: BaseStore) -> PromptSection | None:
    """The plugins the agent can offer; no section when there are none. Like accounts, a plugin
    installed or added to the extras shows from the next epoch."""
    items = [PromptItem(o.name, f"- {o.name}: {o.description}", o.description) for o in await offers.offerable(store)]
    return listed("plugins", f"# Plugins you can offer\n\n{_PLUGINS}\n\n", items, "") if items else None


async def _accounts_section(store: BaseStore) -> PromptSection:
    """Account changes show from the next epoch, like memory: the prompt stays the same within one."""
    items = [
        PromptItem(c.label, f"- email: {c.label} <{c.sender}>" + (" (default)" if c.default else ""), c.sender)
        for c in await accounts.list_accounts(store)
    ]
    return listed("accounts", f"# Accounts\n\n{_ACCOUNTS}\n\n", items, "(none connected)")


async def _profile_section(store: BaseStore, user_id: str) -> PromptSection:
    sections = profile.sections(await profile.load(store, user_id))
    items = [PromptItem(title, profile.line(title, entries), "; ".join(entries)) for title, entries in sections]
    return listed("profile", "# User profile\n\n", items, "(empty so far)")


async def _facts_sections(store: BaseStore, user_id: str, relevant: Sequence[Fact]) -> list[PromptSection]:
    """The basic facts within their budget, past it left out and logged; then the facts the conversation brought up
    that the first section doesn't hold, no section without any."""
    basic, left_out = facts.in_prompt(await facts.load_all(store, user_id), settings.memory_basic_facts_tokens)
    if left_out:
        logger.warning(
            "%s basic facts past the %s-token budget left out of the system prompt: %s",
            len(left_out),
            settings.memory_basic_facts_tokens,
            ", ".join(f.id for f in left_out),
        )
    held = {f.id for f in basic}
    brought = [_fact_item(f) for f in relevant if f.id not in held]
    sections = [listed("facts", f"# Saved facts\n\n{_FACTS}\n\n", [_fact_item(f) for f in basic], "(none yet)")]
    return [*sections, listed("relevant", f"# Relevant facts\n\n{_RELEVANT}\n\n", brought, "")] if brought else sections


def _fact_item(fact: Fact) -> PromptItem:
    return PromptItem(fact.text, facts.line(fact), key=fact.id)


async def _recent_section(store: BaseStore, user_id: str) -> PromptSection:
    recent = await episodes.recent(store, user_id, settings.memory_max_episodes)
    items = [PromptItem(episodes.when(e), episodes.line(e), e.summary) for e in recent]
    return listed("recent", "# Recent conversations\n\n", items, "(none yet)")


def _summary_section(summary: str) -> PromptSection | None:
    text = f"# Conversation so far\n\n{summary}"
    return PromptSection("summary", text, tuple(headed(summary))) if summary else None
