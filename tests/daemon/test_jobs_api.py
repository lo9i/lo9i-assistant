"""Jobs through DaemonClient: list, pause, resume (with a fresh next run), delete."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import Job, JobError
from assistant.core.jobs import store
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER

_LONG_AGO = "2020-01-01T09:00:00+00:00"


@pytest.fixture
async def client(service):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        yield DaemonClient(http)


async def test_list_pause_resume_and_delete(service, client):
    await store.save(service.store, Job("news", "owner", "0 9 * * *", "UTC", "news digest", _LONG_AGO))
    assert [j.name for j in await client.jobs.list()] == ["news"]
    assert not (await client.jobs.set_enabled("news", False)).enabled
    resumed = await client.jobs.set_enabled("news", True)
    assert resumed.enabled and datetime.fromisoformat(resumed.next_run_at) > datetime.now(UTC)
    await client.jobs.delete("news")
    assert await client.jobs.list() == []
    with pytest.raises(JobError):
        await client.jobs.delete("news")


async def test_a_finished_one_time_job_cant_be_resumed(service, client):
    job = Job("stretch", "owner", "", "UTC", "say stretch", _LONG_AGO, enabled=False, one_time=True)
    await store.save(service.store, job)
    with pytest.raises(JobError, match="passed"):
        await client.jobs.set_enabled("stretch", True)
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    await store.save(service.store, Job("later", "owner", "", "UTC", "t", later, enabled=False, one_time=True))
    assert (await client.jobs.set_enabled("later", True)).next_run_at == later
