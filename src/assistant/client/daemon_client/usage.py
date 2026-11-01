from dataclasses import asdict
from typing import Any

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import SpendingStatus, TokenReport, UsageReport
from assistant.core.usage.limits import SpendingLimits, SpendingLimitsError
from assistant.core.usage.log import TokenRow, ToolUsage

_GROUPS = ("by_day", "by_model", "by_purpose", "by_channel", "by_conversation", "by_job", "by_skill", "by_tool")


class UsageApi:
    """Tool and skill usage, the tokens model calls took, and the limits on what they spend."""

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

    async def spending(self) -> SpendingStatus:
        return _spending(await self._transport.request("GET", "/settings/spending-limits"))

    async def set_limits(self, limits: SpendingLimits) -> SpendingStatus:
        """Raises SpendingLimitsError for a limit that isn't more than 0."""
        changed = await self._transport.request(
            "PUT", "/settings/spending-limits", json=asdict(limits), errors={400: SpendingLimitsError}
        )
        return _spending(changed)


def _spending(data: dict[str, Any]) -> SpendingStatus:
    return SpendingStatus(SpendingLimits(**data["limits"]), data["spent_today"])


def _rows(rows: list[dict[str, Any]]) -> list[TokenRow]:
    return [TokenRow(**row) for row in rows]
