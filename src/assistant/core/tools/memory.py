"""Tools the agent uses to manage long-term memory about the user."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore

from assistant.core import conversations
from assistant.core.context import Context, require_recall, require_search, require_store
from assistant.core.conversation.search import Found
from assistant.core.memory import episodes, facts, profile
from assistant.core.memory.embedder import EmbeddingError
from assistant.core.memory.profile import MAX_ITEMS, Section
from assistant.core.tools.registry import register

_FACT_RESULTS = 5
_EPISODE_RESULTS = 3
_MESSAGE_RESULTS = 10


@register("memory")
@tool
async def remember(fact: str, runtime: ToolRuntime[Context]) -> str:
    """Save a detail about the user that stays true (a date, a decision, an account) for future conversations.

    Not for the status of a task or a problem (a bill not paid yet, a fix in progress): conversation summaries
    keep that.

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
    How to do one task ("when I ask for X, show Y") goes in that task's skill, never in the profile:
    how_to_reply is the general style of replies, goals are outcomes the user works toward over weeks or months.
    The profile is about the user's life, never about this assistant (how they use or host it, its tools or ids).
    """
    if len(items) > MAX_ITEMS:
        return f"Not saved: a section holds at most {MAX_ITEMS} items, got {len(items)}. Merge or drop some."
    user_id = runtime.context.user_id
    current = await profile.load(require_store(runtime.store), user_id)
    await profile.save(require_store(runtime.store), user_id, current.model_copy(update={section: items}))
    return f"Profile section {section} now: {'; '.join(items) or '(empty)'}"


@register("memory")
@tool
async def search_memory(query: str, runtime: ToolRuntime[Context]) -> str:
    """Search everything remembered about the user, beyond what this prompt shows.

    Returns the saved facts and past conversation summaries closest in meaning to the query (in any
    language), and messages the user and you wrote in past conversations and scheduled job runs that
    contain the query's words (for exact details: a number, a name, when something came up; try other
    words when nothing fits). Tool outputs aren't searched.
    """
    context = runtime.context
    sections = [
        await _recalled(context, query),
        await _messages(require_store(runtime.store), context, query),
    ]
    return "\n\n".join(sections)


async def _recalled(context: Context, query: str) -> str:
    try:
        found = await require_recall(context).search(context.user_id, query, _FACT_RESULTS, _EPISODE_RESULTS)
    except EmbeddingError as e:
        return f"Saved facts and conversation summaries couldn't be searched: {e}"
    return (
        f"Saved facts:\n{facts.render(found.facts)}\n\nPast conversation summaries:\n{episodes.render(found.episodes)}"
    )


async def _messages(store: BaseStore, context: Context, query: str) -> str:
    found = await require_search(context).search(context.user_id, query, _MESSAGE_RESULTS)
    if not found:
        return "Messages: none with these words."
    titles = await _titles(store, context.user_id, {f.thread_id for f in found})
    return "Messages:\n" + "\n".join(_result(f, titles[f.thread_id]) for f in found)


async def _titles(store: BaseStore, user_id: str, thread_ids: set[str]) -> dict[str, str]:
    """Scheduled job runs aren't listed conversations; they're named after the job."""
    titles = {}
    for thread_id in thread_ids:
        record = await conversations.load(store, user_id, thread_id)
        titles[thread_id] = record.title if record else thread_id
    return titles


def _result(found: Found, title: str) -> str:
    snippet = " ".join(found.snippet.split())
    return f'- {found.at or "unknown time"}, in "{title}", {found.role}: {snippet}'
