"""Tool and skill usage for clients."""

from assistant.core.agent.base import ServiceBase
from assistant.core.usage.log import UsageReport

__all__ = ["UsageMixin", "UsageReport"]


class UsageMixin(ServiceBase):
    async def usage_report(self, days: int = 7) -> UsageReport:
        return await self._storage.usage.report(days)
