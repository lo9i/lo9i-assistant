from typing import Any

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import TokenReport, UsageReport
from assistant.core.usage.log import TokenRow, ToolUsage

_GROUPS = ("by_day", "by_model", "by_purpose", "by_channel", "by_conversation", "by_job", "by_skill", "by_tool")


class UsageApi:
    """Tool and skill usage, and the tokens model calls took."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def report(self, days: int = 7) -> UsageReport:
        data = await self._transport.request("GET", "/usage", params={"days": days})
        return UsageReport(
            data["days"], [ToolUsage(**t) for t in data["tools"]], [ToolUsage(**s) for s in data["skills"]]
        )

    async def tokens(self, days: int = 7) -> TokenReport:
        data = await self._transport.request("GET", "/usage/tokens", params={"days": days})
        groups = {group: _rows(data[group]) for group in _GROUPS}
        return TokenReport(data["days"], TokenRow(**data["total"]), **groups, estimated_calls=data["estimated_calls"])


def _rows(rows: list[dict[str, Any]]) -> list[TokenRow]:
    return [TokenRow(**row) for row in rows]
