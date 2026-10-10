"""When a local MCP server runs: from its first call, until no call has used it, and it has no background
work in progress (core/mcp/background.py), for a while. Its tools
are known from when it last connected (core/mcp/tool_cache.py), so the agent has them while it's
stopped. A server whose tools aren't known yet (just installed or updated) starts at once to learn them.
Remote servers stay connected (core/mcp/hub.py): stopping them saves nothing on this computer."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

from mcp.types import Tool

IDLE_SECONDS = 600


class OnDemand:
    def __init__(
        self, tools: list[Tool], save: Callable[[list[Tool]], Awaitable[None]], idle_seconds: float = IDLE_SECONDS
    ) -> None:
        """`tools` from when it last connected, [] if unknown; `save` keeps them when they change."""
        self.tools = tools
        self._save = save
        self._idle_seconds = idle_seconds
        self._wanted = asyncio.Event()
        self._in_use = 0
        # Background work the server said it started and hasn't finished yet.
        self._working: set[str] = set()
        self._last_used = 0.0
        if not tools:
            self._wanted.set()

    @property
    def wanted(self) -> bool:
        return self._wanted.is_set()

    def want(self) -> None:
        self._wanted.set()

    def rest(self) -> None:
        """Nothing wants it now: it starts again on the next call."""
        self._wanted.clear()

    async def until_wanted(self, stop: asyncio.Event) -> None:
        stopped, wanted = asyncio.ensure_future(stop.wait()), asyncio.ensure_future(self._wanted.wait())
        try:
            await asyncio.wait({stopped, wanted}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopped.cancel()
            wanted.cancel()

    @contextmanager
    def using(self) -> Iterator[None]:
        """A call in progress: the server isn't idle until it ends."""
        self._in_use += 1
        try:
            yield
        finally:
            self._in_use -= 1
            self._used()

    def started_work(self, work: str) -> None:
        self._working.add(work)

    def finished_work(self, work: str) -> None:
        """The idle time counts from now."""
        self._working.discard(work)
        self._used()

    def stopped(self) -> None:
        """The server stopped: the work it had in progress stopped with it."""
        self._working.clear()

    async def learned(self, tools: list[Tool]) -> None:
        """It connected or its tools changed."""
        self.tools = tools
        self._used()
        await self._save(tools)

    async def idle(self) -> None:
        """Returns once no call has used it for the idle time, and no work is in progress, and lets it rest."""
        loop = asyncio.get_running_loop()
        while True:
            left = self._last_used + self._idle_seconds - loop.time()
            if left <= 0 and not self._in_use and not self._working:
                self.rest()
                return
            await asyncio.sleep(left if left > 0 else self._idle_seconds)

    def _used(self) -> None:
        self._last_used = asyncio.get_running_loop().time()
