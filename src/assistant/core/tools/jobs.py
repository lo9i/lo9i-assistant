"""Tools to schedule, change, delete and list jobs that run unattended, repeatedly or once."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.jobs import schedule as cron
from assistant.core.jobs import store
from assistant.core.jobs.schedule import ScheduleError
from assistant.core.jobs.store import Job, JobError, JobState
from assistant.core.tools.registry import register

ListedState = Literal["all", "active", "paused", "done"]
_GROUPS: list[JobState] = ["active", "paused", "done"]
_HEADINGS: dict[JobState, str] = {
    "active": "Active, will run",
    "paused": "Paused, won't run until resumed",
    "done": "Done, one-time jobs that already ran",
}


@register("jobs")
@tool
async def schedule_job(
    name: str,
    task: str,
    runtime: ToolRuntime[Context],
    schedule: str = "",
    at: str = "",
    on_new_mail: bool = False,
    timezone: str = "",
) -> str:
    """Schedule a job that runs by itself, with nobody watching. Give one of `schedule`, `at` or
    `on_new_mail`.

    `name`: a slug like daily-news. `schedule`: a cron expression in the user's time zone, e.g.
    "0 9 * * *" for every day at 09:00 or "30 8 * * 1-5" for weekdays at 08:30. `at`: one run at a
    local date and time, e.g. "2026-09-30T14:05"; work it out from the current time for requests
    like "in 5 minutes". `on_new_mail`: run whenever new email arrives, given the new messages, e.g.
    for "tell me on Telegram when my bank writes". `task`: what to do, e.g. "Run the skill
    news-digest" or "Send the user a Telegram message: stretch". Actions that need approval are
    sent to the user's connected chat channels to approve, and denied when none is connected.
    Replaces a job with the same name.
    """
    timezone = timezone or settings.timezone
    now = datetime.now(UTC)
    try:
        store.check_name(name)
        job = _new_job(name, runtime.context.user_id, task, _Timing(schedule, at, on_new_mail), timezone, now)
    except (JobError, ScheduleError) as e:
        return str(e)
    await store.save(require_store(runtime.store), job)
    return f"Scheduled {name}: {_timing(job, now)}."


@register("jobs")
@tool
async def update_job(
    name: str,
    runtime: ToolRuntime[Context],
    schedule: str = "",
    at: str = "",
    on_new_mail: bool = False,
    task: str = "",
    enabled: bool | None = None,
) -> str:
    """Change when a job runs (cron `schedule`, one run `at` a local date and time, or
    `on_new_mail`), its task, or pause/resume it (enabled=false/true). Empty fields stay as they are."""
    job = await store.load(require_store(runtime.store), runtime.context.user_id, name)
    if job is None:
        return f"No job named {name}."
    now = datetime.now(UTC)
    try:
        _reschedule(job, _Timing(schedule, at, on_new_mail), now)
    except ScheduleError as e:
        return str(e)
    job.task = task or job.task
    job.enabled = job.enabled if enabled is None else enabled
    await store.save(require_store(runtime.store), job)
    return f"Updated {name} ({job.state}): {_timing(job, now)}."


@register("jobs")
@tool
async def delete_job(name: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a scheduled job."""
    deleted = await store.delete(require_store(runtime.store), runtime.context.user_id, name)
    return f"Deleted {name}." if deleted else f"No job named {name}."


@register("jobs", subagents=True)
@tool
async def list_jobs(runtime: ToolRuntime[Context], state: ListedState = "all") -> str:
    """List scheduled jobs in three groups: active (will run), paused (turned off; won't run until
    resumed with update_job enabled=true) and done (one-time jobs that already ran). Only active
    jobs run. `state` lists one group: active, paused or done."""
    jobs = await store.list_jobs(require_store(runtime.store), runtime.context.user_id)
    shown: list[JobState] = [group for group in _GROUPS if state in ("all", group)]
    text = "\n\n".join(filter(None, (_group(g, [j for j in jobs if j.state == g]) for g in shown)))
    return text or ("No scheduled jobs." if state == "all" else f"No {state} jobs.")


@dataclass
class _Timing:
    """When a job runs: at most one is set; none keeps the job's current timing."""

    schedule: str = ""
    at: str = ""
    on_new_mail: bool = False

    @property
    def given(self) -> int:
        return sum(map(bool, (self.schedule, self.at, self.on_new_mail)))


def _new_job(name: str, user_id: str, task: str, timing: _Timing, timezone: str, now: datetime) -> Job:
    """Raises ScheduleError unless exactly one timing is given and valid."""
    if timing.given != 1:
        raise ScheduleError("Give one of a cron `schedule`, a one-time `at` or `on_new_mail`.")
    cron.zone(timezone)
    job = Job(name, user_id, "", timezone, task, "")
    _reschedule(job, timing, now)
    return job


def _reschedule(job: Job, timing: _Timing, now: datetime) -> None:
    """Applies a new timing; with none, a repeating job's next run is recomputed and the others
    keep theirs. Raises ScheduleError."""
    if timing.given > 1:
        raise ScheduleError("Give only one of `schedule`, `at` and `on_new_mail`.")
    if timing.on_new_mail:
        job.schedule, job.one_time, job.on_new_mail, job.next_run_at = "", False, True, ""
        return
    if timing.at:
        job.schedule, job.one_time, job.on_new_mail = "", True, False
        job.next_run_at = cron.parse_at(timing.at, job.timezone, now).astimezone(UTC).isoformat()
        return
    if timing.schedule:
        cron.validate(timing.schedule, job.timezone)
        job.schedule, job.one_time, job.on_new_mail = timing.schedule, False, False
    if job.schedule:
        job.next_run_at = cron.next_runs(job.schedule, job.timezone, now)[0].astimezone(UTC).isoformat()


def _timing(job: Job, now: datetime) -> str:
    if job.on_new_mail:
        return "runs on each new email"
    if job.one_time:
        return cron.describe_once(datetime.fromisoformat(job.next_run_at), job.timezone)
    return cron.describe(job.schedule, job.timezone, now)


def _group(state: JobState, jobs: list[Job]) -> str:
    """Empty when the group has no jobs."""
    if not jobs:
        return ""
    return f"{_HEADINGS[state]} ({len(jobs)}):\n" + "\n".join(f"- {_describe(j)}" for j in jobs)


def _describe(job: Job) -> str:
    return f"{job.name}: {_when(job)}. Task: {job.task}{_last_run(job)}"


def _when(job: Job) -> str:
    if job.state == "done":
        return "ran once, finished"
    if job.on_new_mail:
        return "runs on new email" if job.state == "active" else "runs on new email; won't run until resumed"
    if job.one_time:
        moment = f"once at {_local(job.next_run_at, job.timezone)} ({job.timezone})"
        return f"runs {moment}" if job.state == "active" else f"was to run {moment}; won't run until resumed"
    every = f"cron `{job.schedule}` ({job.timezone})"
    if job.state == "paused":
        return f"{every}; won't run until resumed"
    return f"{every}; next run {_local(job.next_run_at, job.timezone)}"


def _last_run(job: Job) -> str:
    if not job.runs:
        return ". Not run yet."
    last = job.runs[-1]
    summary = f" - {last.summary}" if last.summary else ""
    return f". Last run {_local(last.at, job.timezone)}: {last.status}{summary}"


def _local(timestamp: str, timezone: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(cron.zone(timezone)).strftime("%a %d %b %H:%M")
