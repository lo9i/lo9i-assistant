"""The restart or stop of the daemon that was asked for and waits for the runs in progress (daemon/shutdown.py), as
the rest of lo9i sees it: who asked and when, and what it waits for. While it waits, messages queued in a
conversation (core/conversation/queued.py) aren't sent (daemon/queued.py), so the assistant's own tools need to know
(start_task, list_tasks: core/agent_tasks/tools.py), and so do the apps (GET /system/ending).

It's kept in a small file in the data folder too (RESTART_PENDING_PATH, ~/.lo9i/restart-pending.json), readable
without the daemon: written when one is asked for, deleted when it's taken back and when the daemon starts, so one
left by a daemon that ended never outlives it.

A conversation can have its queued messages go first (`send_first`): a coding task the user chose to send now
although a restart is pending (start_task's `when_restart_pending="send_now"`). The daemon sends them while the
restart waits, and the restart waits for them too, until the conversation has none left and its run ended
(`sent`), so the task's agent works it to its end before the daemon restarts."""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AskedEnding:
    # "restart" or "stop".
    ending: str
    # Who asked: the kind of client and its device, or what in the daemon asked (an update).
    asked_by: str
    # ISO 8601, UTC.
    asked_at: str
    # The conversations with a run in progress, which it waits for.
    waiting_for: list[str] = field(default_factory=list)


class EndingState:
    def __init__(self, path: Path, running: Callable[[], list[str]]) -> None:
        """`running`: the conversations with a run in progress now."""
        self._path = path
        self._running = running
        self._asked: AskedEnding | None = None
        self._first: set[str] = set()
        self._none_first = asyncio.Event()
        self._none_first.set()

    def clear_left_over(self) -> None:
        """At start: a file left by the daemon before is about an ending that has happened."""
        self._path.unlink(missing_ok=True)

    def asked(self, ending: str, by: str) -> None:
        """A restart or stop was asked for; one asked for while another waits takes its place (the latest wins, as
        in daemon/shutdown.py), keeping when the first was asked."""
        at = self._asked.asked_at if self._asked else datetime.now(UTC).isoformat()
        self._asked = AskedEnding(ending, by, at)
        self._write(self.current())

    def taken_back(self) -> None:
        """It won't happen: taken back, or a stop that failed. Nothing has to go first any more."""
        self._asked = None
        self._path.unlink(missing_ok=True)
        self.let_go()

    def send_first(self, thread_id: str) -> None:
        """The conversation's queued messages are sent before a restart or stop, and it waits for their runs."""
        self._first.add(thread_id)
        self._none_first.clear()

    def goes_first(self, thread_id: str) -> bool:
        return thread_id in self._first

    def sent(self, thread_id: str) -> None:
        """The conversation has nothing queued left and no run of it in progress."""
        self._first.discard(thread_id)
        if not self._first:
            self._none_first.set()

    def sending_first(self) -> bool:
        return bool(self._first)

    async def until_sent(self) -> None:
        """Returns once no conversation's queued messages go first."""
        await self._none_first.wait()

    def let_go(self) -> None:
        """It goes ahead now (its runs cancelled) or won't happen: nothing waits for what goes first."""
        self._first.clear()
        self._none_first.set()

    def current(self) -> AskedEnding | None:
        """The one asked for, with the runs it waits for now; None when none is."""
        if self._asked is None:
            return None
        return AskedEnding(self._asked.ending, self._asked.asked_by, self._asked.asked_at, self._running())

    def _write(self, asked: AskedEnding | None) -> None:
        if asked is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(asdict(asked), indent=2))
        except OSError:
            # The state lives in memory all the same; only what reads the file without the daemon misses it.
            logger.exception("Couldn't write %s", self._path)
