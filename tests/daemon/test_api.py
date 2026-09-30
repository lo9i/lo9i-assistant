"""The daemon API through DaemonClient, served in-process (no socket needed)."""

import httpx
import pytest

import assistant.core.integrations.telegram as integration
from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import InvalidNameError, InvalidTokenError
from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired, Done, ToolFinished
from assistant.daemon.api import create_app
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER
from tests.conftest import collect


@pytest.fixture
async def app(service):
    return create_app(service, RunHub())


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "test"}) as http:
        yield DaemonClient(http)


async def test_requests_without_the_client_header_are_refused(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://lo9i") as http:
        assert (await http.get("/health")).status_code == 200
        response = await http.post("/threads")
        assert response.status_code == 403 and "X-Lo9i-Client" in response.text


async def test_send_with_attachment_approve_and_resume(client, script):
    script.call("bash", command="cat notes.txt || true").reply("read it")
    script.call("bash", command="rm -rf build").reply("left it")
    session = await client.session("owner", "cli")
    events = await collect(client.send(session, "read it", [Attachment("notes.txt", "text/plain", b"hi")]))
    assert isinstance(events[1], ToolFinished) and isinstance(events[-1], Done)

    events = await collect(client.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    events = await collect(client.resume(session, {approval.interrupt_id: {"approved": False, "reason": "no"}}))
    assert events[0] == ToolFinished("bash", "The user rejected this (no).")


async def test_threads_memory_and_telegram(client, monkeypatch):
    async def bot_username(token):
        raise InvalidTokenError("Telegram rejected the token: Unauthorized")

    monkeypatch.setattr(integration, "bot_username", bot_username)
    new = await client.new_thread("owner")
    assert (await client.session("owner", "telegram")).thread_id == new
    assert (await client.memory.snapshot()).facts == []
    assert await client.clients.list() == []
    assert not (await client.email.status()).connected
    assert not (await client.telegram.status()).connected
    with pytest.raises(InvalidTokenError):
        await client.telegram.connect("bad")


async def test_unknown_run_is_404(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://lo9i", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.get("/runs/nope/events")).status_code == 404


async def test_skills_and_usage_endpoints(client, script, isolated_settings, monkeypatch):
    from assistant.core.agent import SkillError
    from assistant.core.config import settings
    from assistant.core.skills import store as skills

    monkeypatch.setattr(settings, "skills_dir", str(isolated_settings / "skills"))
    skills.save("news-digest", "Daily news", "1. Search")
    script.call("use_skill", name="news-digest").reply("done")
    await collect(client.send(await client.session("owner", "cli"), "go"))
    assert [s.name for s in await client.skills.list()] == ["news-digest"]
    assert (await client.skills.get("news-digest")).instructions == "1. Search"
    report = await client.usage.report(7)
    assert report.skills[0].name == "news-digest" and report.tools[0].name == "use_skill"
    await client.skills.delete("news-digest")
    with pytest.raises(SkillError):
        await client.skills.get("news-digest")


async def test_rename_the_assistant(client):
    assert await client.identity.name() == ""
    assert await client.identity.rename("  Max   Power ") == "Max Power"
    assert await client.identity.name() == "Max Power"
    with pytest.raises(InvalidNameError):
        await client.identity.rename("x" * 65)
