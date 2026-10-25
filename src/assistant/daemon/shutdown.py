"""Restarting or stopping the daemon on request (Settings → System, `/host`, `assistant daemon restart`, POST
/system/restart and /system/stop). It waits until no run is in progress: an agent a conversation is handed to
(/claude) answers inside a run, so stopping the daemon under it would stop the agent before it replies. While it
waits it's pending (GET /system/ending): it can be taken back, or made to go ahead now by cancelling the runs, so
a run that never ends (a stuck job) can't hold it forever. It waits for an update being installed too
(daemon/updates.py), which no one can cancel: stopped in the middle, the daemon would come back on new code with
what the old one needed. The restart an update asks for once it's installed can't be taken back either: the new
code is in the tree, and the old code still running would load its modules from there.

A restart stops the daemon cleanly and starts the process again in place (`exec_again`), keeping its pid, log
and supervisor, so it's the same however the daemon was started. Stopping depends on what started it
(daemon/managers.py): one started by hand exits, while launchd and systemd would start it again unless stopping
goes through them."""

import asyncio
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from assistant.protocol import NoEndingError, StopRefusedError

logger = logging.getLogger(__name__)


class Ending(StrEnum):
    RESTART = "restart"
    STOP = "stop"


@dataclass(frozen=True)
class Pending:
    ending: Ending
    waiting_for_runs: int


# Tells the apps a restart or stop is coming and how many runs it waits for, or, `taken_back`, that it won't.
Announce = Callable[[Ending, int, bool], None]


class Runs(Protocol):
    """What the service offers (core/agent/runs.py)."""

    def runs_in_progress(self) -> int: ...

    async def until_no_runs(self) -> None: ...

    def cancel_runs(self) -> int: ...


class Update(Protocol):
    """What the updater offers (daemon/updates.py)."""

    def installing(self) -> bool: ...

    async def until_installed(self) -> None: ...


class _NoUpdates:
    def installing(self) -> bool:
        return False

    async def until_installed(self) -> None:
        return


class ServiceManager(Protocol):
    """What started the daemon (daemon/managers.py), and what stopping it takes."""

    def stop_refusal(self) -> str | None:
        """Why the daemon can't be stopped from the app, or None when it can."""
        ...

    async def stop(self, stop: asyncio.Event) -> None:
        """Stops the daemon: sets `stop`, or has the service manager stop it."""
        ...


class Shutdown:
    def __init__(
        self,
        runs: Runs,
        stop: asyncio.Event,
        manager: ServiceManager,
        announce: Announce = lambda ending, waiting, taken_back: None,
        update: Update | None = None,
    ) -> None:
        """`announce` tells the apps a restart or stop is coming, and how many runs it waits for, or that it was
        taken back, so every one of them can say so, not only the one that asked. `update` is the updater, whose
        update in progress it waits for too."""
        self._runs = runs
        self._stop = stop
        self._manager = manager
        self._announce = announce
        self._update = update or _NoUpdates()
        self._wanted = Ending.RESTART
        self._waiting: asyncio.Task | None = None
        # No run is left: it's going ahead, and can't be taken back any more.
        self._going_ahead = False
        # An update was installed: the daemon must end so it runs (`restart_for_update`).
        self._installed = False
        # How the daemon ends, once it does; None until then, and when a signal stopped it.
        self.ending: Ending | None = None

    def request(self, ending: Ending, by: str = "") -> int:
        """Ends the daemon this way once no run is in progress. Returns how many runs it waits for. `by` says
        who asked (a client, an update), for the log. Raises StopRefusedError when asked to stop a daemon that
        can't be."""
        if ending is Ending.STOP and (reason := self._manager.stop_refusal()):
            logger.info("A stop asked for by %s was refused: %s", by or "a client", reason)
            raise StopRefusedError(reason)
        if self._stop.is_set():
            # Already ending (a signal, or one that went ahead): how was decided then.
            logger.info("A %s asked for by %s comes too late: the daemon is already ending.", ending, by or "a client")
            return 0
        # The latest request wins: asked to stop while waiting to restart, it stops.
        self._wanted = ending
        if self._waiting is None:
            self._waiting = asyncio.create_task(self._when_no_runs())
        waiting = self._runs.runs_in_progress()
        logger.info("A %s was asked for by %s; it waits for %s run(s) in progress.", ending, by or "a client", waiting)
        self._announce(ending, waiting, False)
        return waiting

    def restart_for_update(self) -> int:
        """An update was installed: restarts once no run is in progress, so it runs, and can't be taken back. A
        stop asked for before stays a stop: the update runs when the daemon is started again. Returns how many runs
        it waits for."""
        self._installed = True
        if self._waiting is not None and not self._going_ahead and self._wanted is Ending.STOP:
            return self._runs.runs_in_progress()
        return self.request(Ending.RESTART, "an update")

    def pending(self) -> Pending | None:
        """The restart or stop waiting for runs to end, if one is."""
        if self._waiting is None or self._going_ahead:
            return None
        return Pending(self._wanted, self._runs.runs_in_progress())

    def take_back(self, by: str = "") -> None:
        """The daemon keeps running. Raises NoEndingError when no restart or stop is waiting."""
        waiting = self._waiting
        if waiting is None or self._going_ahead:
            raise NoEndingError("No restart or stop is waiting to be taken back.")
        if self._installed:
            raise NoEndingError(
                f"An update was installed, so the {self._wanted} can't be taken back: the assistant runs it once"
                " the runs in progress end. Now cancels them."
            )
        waiting.cancel()
        self._waiting = None
        logger.info("The %s was taken back by %s.", self._wanted, by or "a client")
        self._announce(self._wanted, 0, True)

    def now(self, by: str = "") -> int:
        """Cancels the runs the restart or stop waits for, so it goes ahead now. Returns how many were cancelled.
        Raises NoEndingError when none is waiting."""
        if self.pending() is None:
            raise NoEndingError("No restart or stop is waiting for runs.")
        cancelled = self._runs.cancel_runs()
        logger.info("%s cancelled %s run(s) so the %s goes ahead now.", by or "A client", cancelled, self._wanted)
        return cancelled

    async def _until_nothing_in_progress(self) -> None:
        """No run and no update in progress. Runs may start while an update installs, so it looks again after."""
        while True:
            await self._runs.until_no_runs()
            if not self._update.installing():
                return
            logger.info("The %s waits for the update being installed.", self._wanted)
            await self._update.until_installed()

    async def _when_no_runs(self) -> None:
        await self._until_nothing_in_progress()
        self._going_ahead = True
        logger.info("No run in progress: the %s goes ahead.", self._wanted)
        if self._wanted is Ending.RESTART:
            self.ending = Ending.RESTART
            self._stop.set()
            return
        try:
            await self._manager.stop(self._stop)
        except Exception:
            logger.exception("Couldn't stop the daemon")
            self._waiting, self._going_ahead = None, False
            if self._installed:
                self._restart_instead()
            return
        self.ending = Ending.STOP

    def _restart_instead(self) -> None:
        """A stop that failed after an update was installed: it restarts instead, so the update runs."""
        logger.info("Restarting instead, so the update installed runs.")
        self.request(Ending.RESTART, "an update")


from_dotenv: set[str] = set()
"""The environment variables the daemon took from .env at start, rather than from whatever started it."""


def exec_again() -> None:
    """Replaces this process with a new daemon started the same way, without what .env had added to its
    environment, so the new one reads .env as it is now."""
    for key in from_dotenv:
        os.environ.pop(key, None)
    os.execv(sys.executable, sys.orig_argv)
