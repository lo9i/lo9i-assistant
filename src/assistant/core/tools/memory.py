"""Tools the agent uses to manage long-term memory about the user."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_store
from assistant.core.memory import facts, profile
from assistant.core.memory.profile import MAX_ITEMS, Section
from assistant.core.tools.registry import register


@register("memory")
@tool
async def remember(fact: str, runtime: ToolRuntime[Context]) -> str:
    """Save a one-off fact about the user (an event, a detail, a decision) for future conversations.

    Lasting things about the user (who they are, people, how to reply, routine, goals, interests, dislikes, work)
    go in the profile instead.
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

    Include the items to keep, not only the new ones. At most 8 items: merge or replace when full.
    An instruction about replies ("when I ask for X, show Y") goes in how_to_reply, never in goals:
    goals are outcomes the user works toward over weeks or months.
    """
    if len(items) > MAX_ITEMS:
        return f"Not saved: a section holds at most {MAX_ITEMS} items, got {len(items)}. Merge or drop some."
    user_id = runtime.context.user_id
    current = await profile.load(require_store(runtime.store), user_id)
    await profile.save(require_store(runtime.store), user_id, current.model_copy(update={section: items}))
    return f"Profile section {section} now: {'; '.join(items) or '(empty)'}"
