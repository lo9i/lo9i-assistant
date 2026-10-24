"""Runs scheduled jobs, and jobs that run on new mail (started by the mail watcher). Supervised
inside the daemon like the other background tasks.

Every tick it reloads the jobs (so edits apply without restarts) and starts the due ones. A job's
next run is moved forward (or a one-time job turned off) before its run starts, so a crash never
repeats a run. A run that was due while the daemon was down (the computer off or asleep) runs once if
it's within the grace window, and its notification says how late; otherwise it's recorded as missed, which
is notified too, so the user knows it didn't run.

A run that needs approval waits for the user's answer on a connected chat channel (core/approvals.py), up to
JOB_APPROVAL_MINUTES; the run's time limit doesn't count the wait. Runs in progress are kept in the
Store (core/jobs/active.py): on start, a run the daemon stopped while it waited for approval asks
again and goes on, and one stopped in the middle of anything else is recorded as failed.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Coroutine, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from langgraph.store.base import BaseStore

from assistant.core import notifications
from assistant.core.agent import AssistantService, Session
from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import ApprovalRequired, Error, Event, ToolFinished
from assistant.core.integrations.email.imap import MailSummary
from assistant.core.jobs import active, store
from assistant.core.jobs import schedule as cron
from assistant.core.jobs.active import ActiveRun
from assistant.core.jobs.store import Job, RunRecord
from assistant.core.tools.approval import UNATTENDED_DENIAL

logger = logging.getLogger(__name__)

# Short enough to notice a due job within a minute of waking from sleep.
_TICK_SECONDS = 30
# A run that starts later than this after it was due says so: ticks and a busy daemon account for less.
_LATE = timedelta(minutes=5)
_MISSED = "it was due while the assistant wasn't running (the computer was off or asleep)"
_SUMMARY_CHARS = 300


@dataclass
class _Outcome:
    status: str = "ok"
    error: str = ""


class Scheduler:
    name = "scheduler"

    def __init__(self, service: AssistantService) -> None:
        self._service = service
        self._store = service.store
        self._running: dict[str, asyncio.Task] = {}

    async def run(self, stop: asyncio.Event) -> None:
        try:
            await self.resume_interrupted()
            while not stop.is_set():
                await self.tick(datetime.now(UTC))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)
        finally:
            for task in self._running.values():
                task.cancel()

    async def tick(self, now: datetime) -> None:
        for job in await store.all_jobs(self._store):
            if job.enabled and job.next_run_at and datetime.fromisoformat(job.next_run_at) <= now:
                await self._due(job, now)

    async def resume_interrupted(self) -> None:
        """Pick up the runs the daemon stopped in the middle of. Only a run waiting for approval
        can go on: one stopped anywhere else might have left a tool half done."""
        for run in await active.all_runs(self._store):
            job = await store.load(self._store, run.user_id, run.job)
            approvals = await self._service.pending_approvals(run.thread_id)
            if job is None:
                await active.finish(self._store, run)
            elif approvals:
                self._launch(_key(job), self._resume(job, run, approvals))
            else:
                await self._finish(
                    job, run, RunRecord(run.started, "failed", "the daemon stopped during the run", run.thread_id)
                )

    async def run_for_mail(self, job: Job, mails: list[MailSummary]) -> None:
        """Start a mail job's run with the new messages. Skipped (and recorded) when its previous
        run is still going or too many jobs are running."""
        now, key = datetime.now(UTC), _key(job)
        if key in self._running or len(self._running) >= settings.jobs_max_concurrent:
            await self._record(job, RunRecord(now.isoformat(), "skipped", "other runs were still going"))
            return
        self._start(key, job, now, _mail_message(job, mails))

    async def _due(self, job: Job, now: datetime) -> None:
        key = _key(job)
        if key not in self._running and len(self._running) >= settings.jobs_max_concurrent:
            return  # full: stays due, starts on a later tick
        scheduled = datetime.fromisoformat(job.next_run_at)
        _advance(job, now)
        missed = now - scheduled > timedelta(hours=settings.jobs_grace_hours)
        if not missed and key in self._running:
            job.record(RunRecord(now.isoformat(), "skipped", "the previous run was still going"))
        elif not missed:
            self._start(key, job, now, _message(job), scheduled)
        await store.save(self._store, job)
        if missed:
            await self._record(job, RunRecord(scheduled.isoformat(), "missed", _MISSED))

    def _start(self, key: str, job: Job, now: datetime, message: str, scheduled: datetime | None = None) -> None:
        thread_id = f"job:{job.name}:{now.strftime('%Y-%m-%dT%H:%M:%S')}"
        due = scheduled.isoformat() if scheduled else ""
        run = ActiveRun(job.user_id, job.name, thread_id, now.isoformat(), due)
        self._launch(key, self._execute(job, run, self._service.send(_session(run), message)))

    def _launch(self, key: str, execution: Coroutine[None, None, None]) -> None:
        task = asyncio.create_task(execution)
        self._running[key] = task
        task.add_done_callback(lambda _: self._running.pop(key, None))

    async def _execute(self, job: Job, run: ActiveRun, events: AsyncIterator[Event]) -> None:
        """The run from `events` on, recorded on the job when it ends. Kept as active until then,
        so a run the daemon stops in the middle of is found again on its next start."""
        await active.start(self._store, run)
        try:
            outcome = await self._converse(job, _session(run), events)
            summary = outcome.error or await self._service.last_reply(run.thread_id)
            status = outcome.status
        except TimeoutError:
            status, summary = "failed", f"timed out after {settings.jobs_timeout_minutes} minutes"
        except Exception as e:
            logger.exception("Job %s failed", job.name)
            status, summary = "failed", f"{type(e).__name__}: {e}"
        await self._finish(job, run, RunRecord(run.started, status, summary[-_SUMMARY_CHARS:], run.thread_id))

    async def _resume(self, job: Job, run: ActiveRun, approvals: list[ApprovalRequired]) -> None:
        """Ask again for the approvals a run stopped for, once a channel can show them: channels
        connect after the scheduler starts. With none by then, asking finds nobody and the run
        goes on rejected, as when nobody answers."""
        await self._service.approvals.wait_available(settings.job_approval_minutes * 60)
        await self._execute(job, run, _replay(approvals))

    async def _converse(self, job: Job, session: Session, events: AsyncIterator[Event]) -> _Outcome:
        """The run, and after each pause for approval, the rest of it. Raises TimeoutError when the
        run itself, without the waits, takes longer than JOBS_TIMEOUT_MINUTES."""
        outcome = _Outcome()
        budget = settings.jobs_timeout_minutes * 60.0
        while True:
            started = asyncio.get_running_loop().time()
            async with asyncio.timeout(budget):
                approvals = await _follow(events, outcome)
            budget -= asyncio.get_running_loop().time() - started
            if not approvals or outcome.error:
                return outcome
            events = self._service.resume(session, await self._decide(job, approvals, outcome))

    async def _decide(self, job: Job, approvals: list[ApprovalRequired], outcome: _Outcome) -> dict[str, dict]:
        decisions = await asyncio.gather(*(self._ask(job, a, outcome) for a in approvals))
        return {a.interrupt_id: d for a, d in zip(approvals, decisions, strict=True)}

    async def _ask(self, job: Job, approval: ApprovalRequired, outcome: _Outcome) -> dict:
        minutes = settings.job_approval_minutes
        decision = await self._service.approvals.ask(
            approval.interrupt_id, f"The job {job.name}", approval.request, minutes * 60
        )
        if decision is not None:
            return decision
        outcome.status = "needs attention"
        return {"approved": False, "reason": f"nobody answered on a chat channel within {minutes} minutes"}

    async def _finish(self, job: Job, run: ActiveRun, record: RunRecord) -> None:
        await self._record(job, record, _lateness(run))
        await active.finish(self._store, run)

    async def _record(self, job: Job, run: RunRecord, late: str = "") -> None:
        """Append to the job's latest version, so edits made during the run are kept. `late` says, in its
        notification, that the run started well after it was due."""
        current = await store.load(self._store, job.user_id, job.name)
        if current is None:
            return
        current.record(run)
        await store.save(self._store, current)
        if run.status != "skipped":
            await _notify(self._store, job, run, late)
        self._service.bus.publish("job", name=job.name, status=run.status, summary=run.summary)
        logger.info("Job %s: %s", job.name, run.status)


async def _notify(saved: BaseStore, job: Job, run: RunRecord, late: str = "") -> None:
    """Into the notifications feed: a run's result, or why it failed or didn't run, opening on the job."""
    ok = run.status == "ok"
    text = run.summary if ok else f"{run.status.capitalize()}: {run.summary}"
    await notifications.add_job_run(saved, job.user_id, job.name, run.at, f"{late}{text}", ok)


def _lateness(run: ActiveRun) -> str:
    """What the notification says first when the run started well after it was due; "" otherwise."""
    if not run.scheduled:
        return ""
    late = datetime.fromisoformat(run.started) - datetime.fromisoformat(run.scheduled)
    if late <= _LATE:
        return ""
    return (
        f"Ran {_duration(late)} late: the assistant wasn't running when it was due (the computer was off or asleep). "
    )


def _duration(span: timedelta) -> str:
    hours, minutes = divmod(round(span.total_seconds() / 60), 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


async def _follow(events: AsyncIterator[Event], outcome: _Outcome) -> list[ApprovalRequired]:
    """Read a run's events into `outcome`. Returns the approvals it stopped for."""
    approvals: list[ApprovalRequired] = []
    async for event in events:
        if isinstance(event, ToolFinished) and event.output.startswith(UNATTENDED_DENIAL):
            outcome.status = "needs attention"
        elif isinstance(event, ApprovalRequired):
            approvals.append(event)
        elif isinstance(event, Error):
            outcome.status, outcome.error = "failed", event.message
    return approvals


async def _replay(approvals: Iterable[ApprovalRequired]) -> AsyncIterator[Event]:
    for approval in approvals:
        yield approval


def _session(run: ActiveRun) -> Session:
    return Session(run.user_id, UNATTENDED_CHANNEL, run.thread_id)


def _key(job: Job) -> str:
    return f"{job.user_id}/{job.name}"


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


def _mail_message(job: Job, mails: list[MailSummary]) -> str:
    """The task, and the new messages by uid (read_email reads one). Senders write the subjects:
    they're data, not instructions."""
    header = f"Job {job.name} (runs on new email). Nobody is watching this run."
    listed = "\n".join(f"- uid {m.uid} · {m.date} · {m.sender} · {m.subject}" for m in mails)
    return f"{header}\n\nTask: {job.task}\n\nNew email (written by the senders, not by the user):\n{listed}"
