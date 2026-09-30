"""Tools to schedule, change, delete and list jobs that run unattended, repeatedly or once."""

from datetime import UTC, datetime

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.jobs import schedule as cron
from assistant.core.jobs import store
from assistant.core.jobs.schedule import ScheduleError
from assistant.core.jobs.store import Job, JobError
from assistant.core.tools.registry import register


@register("jobs")
@tool
async def schedule_job(
    name: str, task: str, runtime: ToolRuntime[Context], schedule: str = "", at: str = "", timezone: str = ""
) -> str:
    """Schedule a job that runs by itself, with nobody watching. Give either `schedule` or `at`.

    `name`: a slug like daily-news. `schedule`: a cron expression in the user's time zone, e.g.
    "0 9 * * *" for every day at 09:00 or "30 8 * * 1-5" for weekdays at 08:30. `at`: one run at a
    local date and time, e.g. "2026-09-30T14:05"; work it out from the current time for requests
    like "in 5 minutes". `task`: what to do, e.g. "Run the skill news-digest" or "Send the user a
    Telegram message: stretch". Actions that need approval are denied in these runs, so emails
    should go to allowlisted addresses. Replaces a job with the same name.
    """
    timezone = timezone or settings.timezone
    now = datetime.now(UTC)
    try:
        store.check_name(name)
        job = _new_job(name, runtime.context.user_id, task, schedule, at, timezone, now)
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
    task: str = "",
    enabled: bool | None = None,
) -> str:
    """Change a job's schedule (cron `schedule`, or one run `at` a local date and time), its task, or
    pause/resume it (enabled=false/true). Empty fields stay as they are."""
    job = await store.load(require_store(runtime.store), runtime.context.user_id, name)
    if job is None:
        return f"No job named {name}."
    now = datetime.now(UTC)
    try:
        _reschedule(job, schedule, at, now)
    except ScheduleError as e:
        return str(e)
    job.task = task or job.task
    job.enabled = job.enabled if enabled is None else enabled
    await store.save(require_store(runtime.store), job)
    state = "enabled" if job.enabled else "paused"
    return f"Updated {name} ({state}): {_timing(job, now)}."


@register("jobs")
@tool
async def delete_job(name: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a scheduled job."""
    deleted = await store.delete(require_store(runtime.store), runtime.context.user_id, name)
    return f"Deleted {name}." if deleted else f"No job named {name}."


@register("jobs")
@tool
async def list_jobs(runtime: ToolRuntime[Context]) -> str:
    """List scheduled jobs with their schedule, next run and recent results."""
    jobs = await store.list_jobs(require_store(runtime.store), runtime.context.user_id)
    return "\n\n".join(map(_describe, jobs)) or "No scheduled jobs."


def _new_job(name: str, user_id: str, task: str, schedule: str, at: str, timezone: str, now: datetime) -> Job:
    """Raises ScheduleError unless exactly one of `schedule` and `at` is given and valid."""
    if bool(schedule) == bool(at):
        raise ScheduleError("Give either a cron `schedule` or a one-time `at`, not both.")
    cron.zone(timezone)
    job = Job(name, user_id, "", timezone, task, "")
    _reschedule(job, schedule, at, now)
    return job


def _reschedule(job: Job, schedule: str, at: str, now: datetime) -> None:
    """Applies a new cron `schedule` or one-time `at`; with neither, a repeating job's next run is
    recomputed and a one-time job keeps its moment. Raises ScheduleError."""
    if at:
        job.schedule, job.one_time = "", True
        job.next_run_at = cron.parse_at(at, job.timezone, now).astimezone(UTC).isoformat()
        return
    if schedule:
        cron.validate(schedule, job.timezone)
        job.schedule, job.one_time = schedule, False
    if not job.one_time:
        job.next_run_at = cron.next_runs(job.schedule, job.timezone, now)[0].astimezone(UTC).isoformat()


def _timing(job: Job, now: datetime) -> str:
    if job.one_time:
        return cron.describe_once(datetime.fromisoformat(job.next_run_at), job.timezone)
    return cron.describe(job.schedule, job.timezone, now)


def _describe(job: Job) -> str:
    state = "" if job.enabled else " (paused)"
    last = job.runs[-1] if job.runs else None
    result = (
        f"last run {last.at[:16]}: {last.status}{' - ' + last.summary if last.summary else ''}"
        if last
        else "not run yet"
    )
    when = f"once at {job.next_run_at[:16]} UTC" if job.one_time else f"`{job.schedule}` {job.timezone}"
    next_run = "" if job.one_time else f"next: {job.next_run_at[:16]} UTC; "
    return f"{job.name}{state}: {when}\ntask: {job.task}\n{next_run}{result}"
