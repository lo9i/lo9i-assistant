"""Builds the system prompt at the start of each epoch.

Order runs from stable to volatile: persona, operating instructions, channel hints, then
profile, facts, recent episodes and the running summary. Prompt texts live in `prompts/`.
"""

from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation import prompts
from assistant.core.conversation.persona import load_persona
from assistant.core.memory import episodes, facts, profile

_OPERATING = prompts.load("operating")
_CHANNELS = prompts.load("channels")


async def build_system_prompt(store: BaseStore, user_id: str, conversation_summary: str) -> str:
    sections = [
        await load_persona(),
        _OPERATING,
        f"# Channels\n\n{_CHANNELS}",
        f"# User profile\n\n{profile.render(await profile.load(store, user_id))}",
        f"# Saved facts\n\n{facts.render(await facts.load(store, user_id, settings.memory_max_facts))}",
        f"# Recent conversations\n\n{episodes.render(await episodes.recent(store, user_id, settings.memory_max_episodes))}",
    ]
    if conversation_summary:
        sections.append(f"# Conversation so far\n\n{conversation_summary}")
    return "\n\n".join(sections)
