from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import UsageReport
from assistant.core.usage.log import ToolUsage


class UsageApi:
    """Tool and skill usage statistics."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def report(self, days: int = 7) -> UsageReport:
        data = await self._transport.request("GET", "/usage", params={"days": days})
        return UsageReport(
            data["days"], [ToolUsage(**t) for t in data["tools"]], [ToolUsage(**s) for s in data["skills"]]
        )
