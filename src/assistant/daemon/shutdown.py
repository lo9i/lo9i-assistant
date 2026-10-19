"""Restarting or stopping the daemon on request (Settings → System, `/host`, `assistant daemon restart`, POST
/system/restart and /system/stop). It waits until no run is in progress: an agent a conversation is handed to
(/claude) answers inside a run, so stopping the daemon under it would stop the agent before it replies.

A restart stops the daemon cleanly and starts the process again in place (`exec_again`), keeping its pid, log
and supervisor, so it's the same however the daemon was started. Stopping depends on what started it
(daemon/managers.py): one started by hand exits, while launchd and systemd would start it again unless stopping
goes through them."""

import asyncio
import logging
import os
import sys
from enum import StrEnum
from typing import Protocol

from assistant.protocol import StopRefusedError

logger = logging.getLogger(__name__)


class Ending(StrEnum):
    RESTART = "restart"
    STOP = "stop"


class Runs(Protocol):
    """What the service offers (core/agent/runs.py)."""

    def runs_in_progress(self) -> int: ...

    async def until_no_runs(self) -> None: ...


class ServiceManager(Protocol):
    """What started the daemon (daemon/managers.py), and what stopping it takes."""

    def stop_refusal(self) -> str | None:
        """Why the daemon can't be stopped from the app, or None when it can."""
        ...

    async def stop(self, stop: asyncio.Event) -> None:
        """Stops the daemon: sets `stop`, or has the service manager stop it."""
        ...


class Shutdown:
    def __init__(self, runs: Runs, stop: asyncio.Event, manager: ServiceManager) -> None:
        self._runs = runs
        self._stop = stop
        self._manager = manager
        self._wanted = Ending.RESTART
        self._waiting: asyncio.Task | None = None
        # How the daemon ends, once it does; None until then, and when a signal stopped it.
        self.ending: Ending | None = None

    def request(self, ending: Ending) -> int:
        """Ends the daemon this way once no run is in progress. Returns how many runs it waits for.
        Raises StopRefusedError when asked to stop a daemon that can't be."""
        if ending is Ending.STOP and (reason := self._manager.stop_refusal()):
            raise StopRefusedError(reason)
        # The latest request wins: asked to stop while waiting to restart, it stops.
        self._wanted = ending
        if self._waiting is None:
            self._waiting = asyncio.create_task(self._when_no_runs())
        return self._runs.runs_in_progress()

    async def _when_no_runs(self) -> None:
        await self._runs.until_no_runs()
        if self._wanted is Ending.RESTART:
            self.ending = Ending.RESTART
            self._stop.set()
            return
        try:
            await self._manager.stop(self._stop)
        except Exception:
            logger.exception("Couldn't stop the daemon")
            self._waiting = None
            return
        self.ending = Ending.STOP


def exec_again() -> None:
    """Replaces this process with a new daemon started the same way."""
    os.execv(sys.executable, sys.orig_argv)
