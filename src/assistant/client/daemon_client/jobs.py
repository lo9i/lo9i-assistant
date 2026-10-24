from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Job, JobError
from assistant.core.jobs.store import from_value

# 400: the change isn't possible (a one-time job whose time passed); 404: no such job.
_ERRORS = {400: JobError, 404: JobError}


class JobsApi:
    """Scheduled jobs: list them, pause or resume them, delete them, read a run's full reply."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[Job]:
        return [from_value(j) for j in await self._transport.request("GET", "/jobs")]

    async def set_enabled(self, name: str, enabled: bool) -> Job:
        data = await self._transport.request("PATCH", f"/jobs/{name}", json={"enabled": enabled}, errors=_ERRORS)
        return from_value(data)

    async def run_reply(self, name: str, at: str) -> str:
        """The whole reply of the job's run that started `at`. Raises JobError when there's no such run."""
        data = await self._transport.request("GET", f"/jobs/{name}/reply", params={"at": at}, errors=_ERRORS)
        return data["text"]

    async def delete(self, name: str) -> None:
        await self._transport.request("DELETE", f"/jobs/{name}", errors=_ERRORS)
