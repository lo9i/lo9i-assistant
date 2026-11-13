from typing import Any

import httpx

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import CleanFailure, CleanItem, CleanReport, DiskCategory, DiskReport, UnknownCategoryError

# Measuring walks every folder lo9i keeps and reads its database; cleaning measures again after it.
_MEASURING = httpx.Timeout(300, connect=5)


class DiskApi:
    """The disk lo9i takes by category, and cleaning what can go without losing anything (core/disk/)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def usage(self) -> DiskReport:
        return _report(await self._transport.request("GET", "/system/disk", timeout=_MEASURING))

    async def clean(self, categories: list[str] | None = None) -> CleanReport:
        """Cleans `categories`, or every one but the plugins' downloads when None. Raises UnknownCategoryError."""
        found = await self._transport.request(
            "POST",
            "/system/disk/clean",
            json={"categories": categories or []},
            errors={400: UnknownCategoryError},
            timeout=_MEASURING,
        )
        return CleanReport(
            found["freed"],
            [CleanItem(**i) for i in found["removed"]],
            [CleanFailure(**f) for f in found["failed"]],
            _report(found["usage"]),
        )


def _report(data: dict[str, Any]) -> DiskReport:
    return DiskReport(
        data["home"],
        data["total"],
        data["freeable"],
        [DiskCategory(**c) for c in data["categories"]],
        [CleanItem(**i) for i in data["items"]],
    )
