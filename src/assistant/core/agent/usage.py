"""Usage for clients: tool and skill calls, and the tokens model calls took."""

from assistant.core import conversations
from assistant.core.agent.base import ServiceBase
from assistant.core.config import settings
from assistant.core.usage.log import TokenReport, UsageReport

__all__ = ["TokenReport", "UsageMixin", "UsageReport"]


class UsageMixin(ServiceBase):
    async def usage_report(self, days: int = 7) -> UsageReport:
        return await self._storage.usage.report(days)

    async def token_report(self, days: int = 7) -> TokenReport:
        """Tokens and cost by day, model, purpose, channel, conversation (with titles), job, skill and tool."""
        report = await self._storage.usage.token_report(days)
        titles = {c.thread_id: c.title for c in await conversations.recent(self._storage.store, settings.owner_id)}
        for row in report.by_conversation:
            row.label = titles.get(row.name, "")
        return report
