"""Scheduled jobs as text, shared by the /jobs screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cron_descriptor import Options, get_description

from assistant.core.agent import Job, RunRecord
from assistant_terminal.i18n import day_names, language, short_date, t, translatable

# The cron library's own translations, by the language shown.
_CRON_LOCALES = {"en": "en_US", "es": "es_ES"}
# A run's status as the daemon records it.
_STATUSES = {
    "ok": translatable("ok"),
    "failed": translatable("failed"),
    "needs attention": translatable("needs attention"),
}
# A job's state other than active (core/jobs/).
_STATES = {"paused": translatable("paused"), "done": translatable("done")}


def summary(job: Job) -> str:
    """One line: when it runs, and whether it's on."""
    return f"{timing(job)} · {state(job)}"


def timing(job: Job) -> str:
    if job.on_new_mail:
        return t("on each new email")
    if job.one_time:
        return t("once at {when}", when=_local(job.next_run_at, job.timezone))
    return f"{frequency(job.schedule)} (`{job.schedule}`, {job.timezone})"


def frequency(schedule: str) -> str:
    """The cron schedule in words: "Every 15 minutes", "At 08:30, Monday through Friday"."""
    options = Options()
    options.use_24hour_time_format = True
    options.locale_code = _CRON_LOCALES[language()]
    text = day_names(get_description(schedule, options))
    # A daily schedule reads "At 09:00", which doesn't say how often.
    daily = schedule.split()[2:] == ["*", "*", "*"] and get_description(schedule, _english()).startswith("At ")
    return t("{schedule}, every day", schedule=text) if daily else text


def state(job: Job) -> str:
    if job.state == "active" and job.on_new_mail:
        return t("waiting for mail")
    if job.state == "active":
        return t("next {when}", when=_local(job.next_run_at, job.timezone))
    return t(_STATES[job.state]) if job.state in _STATES else job.state


def describe(job: Job) -> str:
    """Markdown: the job's task, timing and recent runs, newest first."""
    runs = "\n".join(_run(r, job.timezone) for r in reversed(job.runs)) or t("Not run yet.")
    when = f"**{t('Runs:')}** {timing(job)}, {state(job)}"
    return f"### {job.name}\n\n{job.task}\n\n{when}\n\n**{t('Recent runs')}**\n\n{runs}"


def with_reply(job: Job, at: str, reply: str) -> str:
    """The job's description with the whole reply of its run that started `at`."""
    return f"{describe(job)}\n\n**{t('Reply of {when}', when=_local(at, job.timezone))}**\n\n{reply}"


def status(value: str) -> str:
    """A run's status in the language shown."""
    return t(_STATUSES[value]) if value in _STATUSES else value


def _run(run: RunRecord, timezone: str) -> str:
    detail = f": {run.summary}" if run.summary else ""
    return f"- {_local(run.at, timezone)} **{status(run.status)}**{detail}"


def _english() -> Options:
    options = Options()
    options.use_24hour_time_format = True
    return options


def _local(timestamp: str, timezone: str) -> str:
    return short_date(datetime.fromisoformat(timestamp).astimezone(ZoneInfo(timezone)))
