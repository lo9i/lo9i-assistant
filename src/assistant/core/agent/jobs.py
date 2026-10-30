"""Scheduled jobs for clients: list them, pause or resume them, delete them, read a run's whole reply. The
agent creates and edits jobs with its tools (core/tools/jobs.py); store writes tell clients about every change."""

from datetime import UTC, datetime

from langchain_core.messages import AIMessage

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import choices
from assistant.core.i18n import said
from assistant.core.jobs import schedule as cron
from assistant.core.jobs import store
from assistant.core.jobs.store import Job, JobError, RunRecord

__all__ = ["Job", "JobError", "JobsMixin", "RunRecord"]


class JobsMixin(ServiceBase):
    async def list_jobs(self, user_id: str) -> list[Job]:
        return await store.list_jobs(self._storage.store, user_id)

    async def set_job_enabled(self, user_id: str, name: str, enabled: bool) -> Job:
        """Pause or resume. A resumed job runs next at its next time from now, not at a time
        that passed while it was paused. Raises JobError."""
        job = await self._job(user_id, name)
        if enabled and not job.enabled:
            _resume(job, datetime.now(UTC))
        job.enabled = enabled
        await store.save(self._storage.store, job)
        return job

    async def job_run_reply(self, user_id: str, name: str, at: str) -> str:
        """The whole reply of the job's run that started at `at` (its record keeps only the end of it), or
        its summary when it has none (a run skipped, missed or failed before replying). Raises JobError."""
        job = await self._job(user_id, name)
        run = next((r for r in job.runs if r.at == at), None)
        if run is None:
            raise JobError(said("{name} has no run at {at}.", name=name, at=at))
        reply = await self._last_reply(run.thread_id) if run.thread_id and run.status == "ok" else ""
        return reply or run.summary

    async def _last_reply(self, thread_id: str) -> str:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        replies = [m for m in state.values.get("messages", []) if isinstance(m, AIMessage)]
        return choices.without_markers(replies[-1].text).strip() if replies else ""

    async def delete_job(self, user_id: str, name: str) -> None:
        """Raises JobError if it doesn't exist."""
        if not await store.delete(self._storage.store, user_id, name):
            raise JobError(said("No job named {name}.", name=name))

    async def _job(self, user_id: str, name: str) -> Job:
        job = await store.load(self._storage.store, user_id, name)
        if job is None:
            raise JobError(said("No job named {name}.", name=name))
        return job


def _resume(job: Job, now: datetime) -> None:
    if job.on_new_mail:
        return
    if not job.one_time:
        job.next_run_at = cron.next_runs(job.schedule, job.timezone, now)[0].astimezone(UTC).isoformat()
    elif datetime.fromisoformat(job.next_run_at) <= now:
        raise JobError(
            said("{name} was due once and that time has passed. Ask the assistant for a new time.", name=job.name)
        )
