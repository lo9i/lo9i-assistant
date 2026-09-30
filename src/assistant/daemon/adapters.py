"""Channel adapters (Telegram, and later others) run inside the daemon as supervised tasks.

An adapter that crashes is logged and restarted after a pause, without affecting the rest.
"""

import asyncio
import contextlib
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_RESTART_SECONDS = 10


class Adapter(Protocol):
    name: str

    async def run(self, stop: asyncio.Event) -> None:
        """Run until `stop` is set."""
        ...


async def supervise(adapter: Adapter, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await adapter.run(stop)
        except Exception:
            logger.exception("Adapter %s crashed; restarting in %ss", adapter.name, _RESTART_SECONDS)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_RESTART_SECONDS)
