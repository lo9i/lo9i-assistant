import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any
from urllib.parse import quote, urlencode

from assistant.client.daemon_client.reconnect import ReconnectPolicy, resumable_events
from assistant.client.daemon_client.transport import Transport
from assistant.core.logs import LogEntry, LogFileInfo, LogOptions, LogPage, LogQueryError

# Followed while a screen is open, so it waits out a daemon restart; each reconnection starts with a page.
_RECONNECT = ReconnectPolicy(delay_seconds=2)


class LogsApi:
    """The daemon's log files: the latest entries, or following one live."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def options(self) -> LogOptions:
        data = await self._transport.request("GET", "/logs")
        return LogOptions([LogFileInfo(**f) for f in data["files"]], data["levels"], data["components"])

    async def page(self, name: str, level: str = "", component: str = "", lines: int = 100) -> LogPage:
        """`level` and `component` empty for all. Raises LogQueryError for an unknown file or component."""
        path = f"{_file(name)}?{_query(level, component, lines)}"
        return _page(await self._transport.request("GET", path, errors={400: LogQueryError, 404: LogQueryError}))

    async def follow(
        self, name: str, level: str = "", component: str = "", lines: int = 100
    ) -> AsyncGenerator[LogPage | LogEntry]:
        """A page like `page`, then each new matching entry, for as long as the caller reads; after a
        reconnection, a new page. Raises httpx.HTTPStatusError for an unknown file or component."""
        path = f"{_file(name)}/follow?{_query(level, component, lines)}"
        # Closed with this generator, so the connection ends when the caller stops reading.
        async with aclosing(resumable_events(self._transport, path, _RECONNECT, after="")) as events:
            async for kind, data in events:
                yield LogEntry(**json.loads(data)) if kind == "entry" else _page(json.loads(data))


def _file(name: str) -> str:
    return f"/logs/{quote(name, safe='')}"


def _query(level: str, component: str, lines: int) -> str:
    params = {"lines": lines} | ({"level": level} if level else {}) | ({"component": component} if component else {})
    return urlencode(params)


def _page(data: dict[str, Any]) -> LogPage:
    return LogPage(LogFileInfo(**data["file"]), [LogEntry(**e) for e in data["entries"]])
