"""Scheduled jobs as text, shared by the /jobs screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Job, RunRecord


def summary(job: Job) -> str:
    """One line: when it runs, and whether it's on."""
    return f"{timing(job)} · {state(job)}"


def timing(job: Job) -> str:
    if job.one_time:
        return f"once at {_local(job.next_run_at, job.timezone)}"
    return f"`{job.schedule}` ({job.timezone})"


def state(job: Job) -> str:
    if job.enabled:
        return f"next {_local(job.next_run_at, job.timezone)}"
    return "done" if job.one_time and job.runs else "paused"


def describe(job: Job) -> str:
    """Markdown: the job's task, timing and recent runs, newest first."""
    runs = "\n".join(_run(r, job.timezone) for r in reversed(job.runs)) or "Not run yet."
    return f"### {job.name}\n\n{job.task}\n\n**Runs:** {timing(job)}, {state(job)}\n\n**Recent runs**\n\n{runs}"


def _run(run: RunRecord, timezone: str) -> str:
    detail = f": {run.summary}" if run.summary else ""
    return f"- {_local(run.at, timezone)} **{run.status}**{detail}"


def _local(timestamp: str, timezone: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(timezone)).strftime("%a %d %b %H:%M")
