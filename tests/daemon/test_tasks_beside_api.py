"""The routes of the coding tasks beside a conversation, as the apps use them: a conversation's sessions listed,
one's tasks and steps read, writing to its agent, stopping it and taking it off the panel once it ended."""

import httpx
import pytest

from lo9i.client.daemon_client import DaemonClient
from lo9i.core.agent import SessionNotFoundError, TasksBesideError
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER
from tests.core.test_tasks_beside import _session_id, _started, _turns, _until
from tests.core.test_tasks_beside import service as beside_service

service = beside_service


@pytest.fixture
async def http(service):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}) as h:
        yield h


async def test_a_session_is_listed_read_written_to_stopped_and_removed(http, service, script, tmp_path):
    client = DaemonClient(http)
    session = await _started(service, script, tmp_path, "sleep")
    session_id = await _session_id(service, session)
    [listed] = await client.tasks.sessions(session.thread_id)
    assert (listed.id, listed.status) == (session_id, "running")
    details = (await http.get(f"/conversations/{session.thread_id}/tasks/{session_id}")).json()
    assert [(t["asked"], t["from_user"]) for t in details["turns"]] == [("sleep", False)]
    empty = await http.post(f"/conversations/{session.thread_id}/tasks/{session_id}/messages", json={"text": " "})
    assert empty.status_code == 400
    assert await client.tasks.message(session.thread_id, session_id, "and the docs") == "later"
    with pytest.raises(TasksBesideError):
        await client.tasks.remove(session.thread_id, session_id)
    stopped = await client.tasks.stop(session.thread_id, session_id)
    assert stopped.status == "stopped" and stopped.ended_at >= stopped.started_at
    # What it couldn't take goes on as its next task.
    await _until(lambda: _turns(service, session, session_id, 2, "done"))
    await client.tasks.remove(session.thread_id, session_id)
    assert await client.tasks.sessions(session.thread_id) == []
    assert (await http.get(f"/conversations/{session.thread_id}/tasks/{session_id}")).status_code == 404
    with pytest.raises(SessionNotFoundError):
        await client.tasks.message(session.thread_id, session_id, "hello?")


async def test_every_conversations_sessions_are_listed_with_their_conversation(http, service, script, tmp_path):
    client = DaemonClient(http)
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    first = await _started(service, script, tmp_path / "a", "sleep", title="First")
    second = await _started(service, script, tmp_path / "b", "sleep", title="Second")
    listed = await client.tasks.everywhere()
    assert {(s.title, s.thread_id) for s in listed} == {("First", first.thread_id), ("Second", second.thread_id)}
    assert [s.started_at for s in listed] == sorted((s.started_at for s in listed), reverse=True)
    assert [s.ended_at for s in listed] == ["", ""]
    found = {s.thread_id: s for s in listed}
    details = await client.tasks.session(first.thread_id, found[first.thread_id].id)
    assert (details.session.thread_id, [t.asked for t in details.turns]) == (first.thread_id, ["sleep"])
    for session in (first, second):
        await client.tasks.stop(session.thread_id, found[session.thread_id].id)
