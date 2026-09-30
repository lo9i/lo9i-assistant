"""Runs scheduled jobs. Supervised inside the daemon like a channel adapter.

Every tick it reloads the jobs (so edits apply without restarts) and starts the due ones. A job's
next run is moved forward (or a one-time job turned off) before its run starts, so a crash never
repeats a run. A run that was
due while the daemon was down runs once if it's within the grace window, otherwise it's recorded
as missed.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta

from assistant.core.agent import AssistantService, Session
from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import Error, ToolFinished
from assistant.core.jobs import schedule as cron
from assistant.core.jobs import store
from assistant.core.jobs.store import Job, RunRecord
from assistant.core.tools.approval import UNATTENDED_DENIAL

logger = logging.getLogger(__name__)

# Short enough to notice a due job within a minute of waking from sleep.
_TICK_SECONDS = 30
_SUMMARY_CHARS = 300


class Scheduler:
    name = "scheduler"

    def __init__(self, service: AssistantService) -> None:
        self._service = service
        self._store = service.store
        self._running: dict[str, asyncio.Task] = {}

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                await self.tick(datetime.now(UTC))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)
        finally:
            for task in self._running.values():
                task.cancel()

    async def tick(self, now: datetime) -> None:
        for job in await store.all_jobs(self._store):
            if job.enabled and datetime.fromisoformat(job.next_run_at) <= now:
                await self._due(job, now)

    async def _due(self, job: Job, now: datetime) -> None:
        key = f"{job.user_id}/{job.name}"
        if key not in self._running and len(self._running) >= settings.jobs_max_concurrent:
            return  # full: stays due, starts on a later tick
        scheduled = datetime.fromisoformat(job.next_run_at)
        _advance(job, now)
        if now - scheduled > timedelta(hours=settings.jobs_grace_hours):
            job.record(RunRecord(scheduled.isoformat(), "missed", "the daemon wasn't running"))
        elif key in self._running:
            job.record(RunRecord(now.isoformat(), "skipped", "the previous run was still going"))
        else:
            self._start(key, job, now)
        await store.save(self._store, job)

    def _start(self, key: str, job: Job, now: datetime) -> None:
        task = asyncio.create_task(self._execute(job, now))
        self._running[key] = task
        task.add_done_callback(lambda _: self._running.pop(key, None))

    async def _execute(self, job: Job, started: datetime) -> None:
        thread_id = f"job:{job.name}:{started.strftime('%Y-%m-%dT%H:%M')}"
        session = Session(job.user_id, UNATTENDED_CHANNEL, thread_id)
        try:
            async with asyncio.timeout(settings.jobs_timeout_minutes * 60):
                status, error = await self._outcome(self._service.send(session, _message(job)))
            summary = error or await self._service.last_reply(thread_id)
        except TimeoutError:
            status, summary = "failed", f"timed out after {settings.jobs_timeout_minutes} minutes"
        except Exception as e:
            logger.exception("Job %s failed", job.name)
            status, summary = "failed", f"{type(e).__name__}: {e}"
        await self._record(job, RunRecord(started.isoformat(), status, summary[-_SUMMARY_CHARS:], thread_id))

    @staticmethod
    async def _outcome(events) -> tuple[str, str]:
        """(status, error message); the summary comes from the run's last reply."""
        status = "ok"
        async for event in events:
            if isinstance(event, ToolFinished) and event.output.startswith(UNATTENDED_DENIAL):
                status = "needs attention"
            elif isinstance(event, Error):
                return "failed", event.message
        return status, ""

    async def _record(self, job: Job, run: RunRecord) -> None:
        """Append to the job's latest version, so edits made during the run are kept."""
        current = await store.load(self._store, job.user_id, job.name)
        if current is None:
            return
        current.record(run)
        await store.save(self._store, current)
        self._service.bus.publish("job", name=job.name, status=run.status, summary=run.summary)
        logger.info("Job %s: %s", job.name, run.status)


def _advance(job: Job, now: datetime) -> None:
    """Move past this run: a repeating job to its next time, a one-time job to off."""
    if job.one_time:
        job.enabled = False
    else:
        job.next_run_at = cron.next_runs(job.schedule, job.timezone, now)[0].astimezone(UTC).isoformat()


def _message(job: Job) -> str:
    timing = "runs once" if job.one_time else f"runs {job.schedule}, {job.timezone}"
    header = f"Scheduled job {job.name} ({timing}). Nobody is watching this run."
    return f"{header}\n\nTask: {job.task}"
