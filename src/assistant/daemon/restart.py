"""Restarting the daemon on request (`assistant daemon restart`, POST /system/restart), so code changes take
effect. It waits until no run is in progress: an agent a conversation is handed to (/claude) answers inside
a run, so stopping the daemon under it would stop the agent before it replies. Then the daemon stops
cleanly and the process starts again in place (`exec_again`), keeping its pid, log and supervisor."""

import asyncio
import os
import sys
from typing import Protocol


class Runs(Protocol):
    """What the service offers (core/agent/runs.py)."""

    def runs_in_progress(self) -> int: ...

    async def until_no_runs(self) -> None: ...


class Restart:
    def __init__(self, runs: Runs, stop: asyncio.Event) -> None:
        self._runs = runs
        self._stop = stop
        self._waiting: asyncio.Task | None = None
        self.requested = False

    def request(self) -> int:
        """Restarts once no run is in progress. Returns how many runs it waits for."""
        if self._waiting is None:
            self._waiting = asyncio.create_task(self._when_no_runs())
        return self._runs.runs_in_progress()

    async def _when_no_runs(self) -> None:
        await self._runs.until_no_runs()
        self.requested = True
        self._stop.set()


def exec_again() -> None:
    """Replaces this process with a new daemon started the same way."""
    os.execv(sys.executable, sys.orig_argv)
