"""The background subagents' routes, as the apps use them: a conversation's listed, one's steps read, what it waits
for answered, stopping it and removing it once it ended."""

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import SubagentError
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER
from tests.core.test_background_subagents import _sent_off, _status, _until, _working


@pytest.fixture
async def client(service):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}) as h:
        yield DaemonClient(h)


async def test_one_is_listed_answered_and_removed_once_it_ended(client, service, script):
    session, subagent_id = await _sent_off(service, script)
    script.call("bash", command="rm -rf build").reply("Removed.")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        [listed] = await client.subagents.list(session.thread_id)
        assert (listed.id, listed.status, listed.task) == (subagent_id, "waiting", "dig")
        assert [s.id for s in await client.subagents.list()] == [subagent_id]
        assert await client.subagents.list("another") == []
        [asked] = listed.waiting
        await _until(lambda: service.approvals._waiting)
        after = service.bus.last_id
        assert await client.subagents.answer(subagent_id, asked.interrupt_id, {"approved": True})
        await _status(service, after, "done")
    details = await client.subagents.get(subagent_id)
    assert details.subagent.result == "Removed." and [s.name for s in details.steps] == ["bash"]
    with pytest.raises(SubagentError):
        await client.subagents.stop(subagent_id)
    await client.subagents.remove(subagent_id)
    with pytest.raises(SubagentError):
        await client.subagents.get(subagent_id)


async def test_one_working_is_stopped_and_cant_be_removed_until_then(client, service, script):
    _, subagent_id = await _sent_off(service, script)
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        with pytest.raises(SubagentError, match="still working"):
            await client.subagents.remove(subagent_id)
        await client.subagents.stop(subagent_id)
    assert (await client.subagents.get(subagent_id)).subagent.status == "stopped"
