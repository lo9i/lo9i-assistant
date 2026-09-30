"""Tools the agent uses to manage long-term memory about the user."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_store
from assistant.core.memory import facts, profile
from assistant.core.memory.profile import Section
from assistant.core.tools.registry import register


@register("memory")
@tool
async def remember(fact: str, runtime: ToolRuntime[Context]) -> str:
    """Save a one-off fact about the user (an event, a detail, a decision) for future conversations.

    Lasting traits (wants, likes, dislikes, interests, technical level, projects, work) go in the profile instead.
    """
    fact_id = await facts.add(require_store(runtime.store), runtime.context.user_id, fact)
    return f"Saved as {fact_id}."


@register("memory")
@tool
async def forget(fact_id: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a saved fact that is wrong or outdated, by its id."""
    await facts.remove(require_store(runtime.store), runtime.context.user_id, fact_id)
    return f"Deleted {fact_id}."


@register("memory")
@tool
async def update_profile(section: Section, items: list[str], runtime: ToolRuntime[Context]) -> str:
    """Replace one section of the user's profile with the full new list of items.

    Include the items to keep, not only the new ones.
    """
    user_id = runtime.context.user_id
    current = await profile.load(require_store(runtime.store), user_id)
    await profile.save(require_store(runtime.store), user_id, current.model_copy(update={section: items}))
    return f"Profile section {section} now: {'; '.join(items) or '(empty)'}"
