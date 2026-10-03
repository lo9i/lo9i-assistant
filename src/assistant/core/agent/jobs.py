"""Scheduled jobs for clients: list them, pause or resume them, delete them. The agent creates and
edits jobs with its tools (core/tools/jobs.py); store writes tell clients about every change."""

from datetime import UTC, datetime

from assistant.core.agent.base import ServiceBase
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

    async def delete_job(self, user_id: str, name: str) -> None:
        """Raises JobError if it doesn't exist."""
        if not await store.delete(self._storage.store, user_id, name):
            raise JobError(f"No job named {name}.")

    async def _job(self, user_id: str, name: str) -> Job:
        job = await store.load(self._storage.store, user_id, name)
        if job is None:
            raise JobError(f"No job named {name}.")
        return job


def _resume(job: Job, now: datetime) -> None:
    if job.on_new_mail:
        return
    if not job.one_time:
        job.next_run_at = cron.next_runs(job.schedule, job.timezone, now)[0].astimezone(UTC).isoformat()
    elif datetime.fromisoformat(job.next_run_at) <= now:
        raise JobError(f"{job.name} was due once and that time has passed. Ask the assistant for a new time.")
