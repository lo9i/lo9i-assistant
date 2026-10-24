"""Usage for clients: tool and skill calls, the tokens model calls took, and one conversation's stats."""

from dataclasses import dataclass

from assistant.core import conversations
from assistant.core.agent.conversations import ConversationsMixin
from assistant.core.config import settings
from assistant.core.conversation import handoffs
from assistant.core.conversation.epochs import estimate_tokens
from assistant.core.usage.log import TokenReport, UsageReport

__all__ = ["ConversationStats", "TokenReport", "UsageMixin", "UsageReport"]

# What counts as a message in a conversation's stats: what the user and the assistant said, not tool calls.
_MESSAGE_ROLES = ("user", "assistant")


@dataclass(frozen=True)
class ConversationStats:
    """`input_tokens` counts the cache reads too. The times are None for a conversation not in the list
    (a new one before its first message). The context is the assistant's or, while the conversation is handed
    to an agent, that agent's (`context_agent` its name), as of its last answer; 0 when it's not known."""

    thread_id: str
    messages: int
    model_calls: int
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    tool_calls: int
    started_at: str | None
    last_activity: str | None
    context_tokens: int = 0
    context_limit: int = 0
    context_agent: str = ""


class UsageMixin(ConversationsMixin):
    async def usage_report(self, days: int = 7) -> UsageReport:
        return await self._storage.usage.report(days)

    async def token_report(self, days: int = 7) -> TokenReport:
        """Tokens and cost by day, model, purpose, channel, conversation (with titles), job, skill and tool."""
        report = await self._storage.usage.token_report(days)
        titles = {c.thread_id: c.title for c in await conversations.recent(self._storage.store, settings.owner_id)}
        for row in report.by_conversation:
            row.label = titles.get(row.name, "")
        return report

    async def conversation_stats(self, user_id: str, thread_id: str) -> ConversationStats:
        """Its messages, the tokens and tool calls it took, and when it started and was last written in."""
        shown = await self.conversation_messages(thread_id)
        usage = await self._storage.usage.thread_usage(thread_id)
        listed = await conversations.load(self._storage.store, user_id, thread_id)
        context, limit, agent = await self._context(user_id, thread_id)
        return ConversationStats(
            thread_id=thread_id,
            messages=sum(m.role in _MESSAGE_ROLES for m in shown),
            model_calls=usage.model_calls,
            input_tokens=usage.input_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            output_tokens=usage.output_tokens,
            tool_calls=usage.tool_calls,
            started_at=listed.started_at if listed else None,
            last_activity=listed.updated_at if listed else None,
            context_tokens=context,
            context_limit=limit,
            context_agent=agent,
        )

    async def _context(self, user_id: str, thread_id: str) -> tuple[int, int, str]:
        """The tokens in the conversation's context, its limit, and the agent's name when it's an agent's."""
        handoff = await handoffs.current(self._storage.store, user_id, thread_id)
        if handoff is not None:
            used = await self.agent_tasks.context(handoff.server, thread_id, handoff.folder)
            return (used.tokens, used.window, handoff.name) if used else (0, 0, handoff.name)
        state = (await self._graph.aget_state({"configurable": {"thread_id": thread_id}})).values
        return (estimate_tokens(state) if state.get("messages") else 0), settings.epoch_max_tokens, ""
