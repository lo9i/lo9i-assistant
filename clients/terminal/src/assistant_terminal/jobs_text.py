"""Scheduled jobs as text, shared by the /jobs screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cron_descriptor import Options, get_description

from assistant.core.agent import Job, RunRecord

_CRON_TEXT = Options()
_CRON_TEXT.use_24hour_time_format = True


def summary(job: Job) -> str:
    """One line: when it runs, and whether it's on."""
    return f"{timing(job)} · {state(job)}"


def timing(job: Job) -> str:
    if job.on_new_mail:
        return "on each new email"
    if job.one_time:
        return f"once at {_local(job.next_run_at, job.timezone)}"
    return f"{frequency(job.schedule)} (`{job.schedule}`, {job.timezone})"


def frequency(schedule: str) -> str:
    """The cron schedule in words: "Every 15 minutes", "At 08:30, Monday through Friday"."""
    text = get_description(schedule, _CRON_TEXT)
    # A daily schedule reads "At 09:00", which doesn't say how often.
    return f"{text}, every day" if schedule.split()[2:] == ["*", "*", "*"] and text.startswith("At ") else text


def state(job: Job) -> str:
    if job.state == "active" and job.on_new_mail:
        return "waiting for mail"
    if job.state == "active":
        return f"next {_local(job.next_run_at, job.timezone)}"
    return job.state


def describe(job: Job) -> str:
    """Markdown: the job's task, timing and recent runs, newest first."""
    runs = "\n".join(_run(r, job.timezone) for r in reversed(job.runs)) or "Not run yet."
    return f"### {job.name}\n\n{job.task}\n\n**Runs:** {timing(job)}, {state(job)}\n\n**Recent runs**\n\n{runs}"


def _run(run: RunRecord, timezone: str) -> str:
    detail = f": {run.summary}" if run.summary else ""
    return f"- {_local(run.at, timezone)} **{run.status}**{detail}"


def _local(timestamp: str, timezone: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(timezone)).strftime("%a %d %b %H:%M")
