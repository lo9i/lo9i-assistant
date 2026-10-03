"""Builds the system prompt at the start of each epoch.

Order runs from stable to volatile: persona, the assistant's name, operating instructions, channel hints,
skills, connected accounts, then profile, facts, recent episodes and the running summary. Prompt texts live in
`prompts/`.
"""

import asyncio

from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation import prompts
from assistant.core.conversation.persona import load_persona
from assistant.core.integrations import email
from assistant.core.memory import episodes, facts, profile
from assistant.core.skills import store as skills

_OPERATING = prompts.load("operating")
_CHANNELS = prompts.load("channels")
_NAME = prompts.load("name")
_ACCOUNTS = prompts.load("accounts")


async def build_system_prompt(store: BaseStore, user_id: str, name: str, conversation_summary: str) -> str:
    recent = await episodes.recent(store, user_id, settings.memory_max_episodes)
    sections = [
        await load_persona(),
        *([_NAME.format(name=name)] if name else []),
        _OPERATING,
        f"# Channels\n\n{_CHANNELS}",
        f"# Skills\n\n{await _skills_index()}",
        f"# Accounts\n\n{await _accounts_index(store)}",
        f"# User profile\n\n{profile.render(await profile.load(store, user_id))}",
        f"# Saved facts\n\n{facts.render(await facts.load(store, user_id, settings.memory_max_facts))}",
        f"# Recent conversations\n\n{episodes.render(recent)}",
    ]
    if conversation_summary:
        sections.append(f"# Conversation so far\n\n{conversation_summary}")
    return "\n\n".join(sections)


async def _skills_index() -> str:
    listed = await asyncio.to_thread(skills.list_skills)
    lines = "\n".join(f"- {s.name}: {s.description}" for s in listed)
    return f"To run a skill, call use_skill with its name and follow the instructions.\n\n{lines or '(none yet)'}"


async def _accounts_index(store: BaseStore) -> str:
    """Account changes show from the next epoch, like memory: the prompt stays the same within one."""
    lines = [
        f"- email: {c.label} <{c.sender}>" + (" (default)" if c.default else "")
        for c in await email.list_accounts(store)
    ]
    return f"{_ACCOUNTS}\n\n" + ("\n".join(lines) or "(none connected)")
