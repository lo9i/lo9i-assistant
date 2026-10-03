"""The daemon API through DaemonClient, served in-process (no socket needed)."""

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

import assistant.core.integrations.telegram.connection as integration
from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import InvalidNameError, InvalidTokenError, Session, SlackError, SpeechSettingsError
from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired, Cancelled, Done, ToolFinished
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER, StartupStatus
from tests.conftest import collect, written


@pytest.fixture
async def app(service):
    return create_app(service, RunHub())


@pytest.fixture
async def client(app):
    """As the terminal app: on the trusted Unix socket."""
    transport = httpx.ASGITransport(app=trusted(app))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "test", CLIENT_ID_HEADER: "me"}
    ) as http:
        yield DaemonClient(http)


async def test_requests_without_the_client_header_are_refused(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
        assert (await http.get("/health")).status_code == 200
        response = await http.post("/threads")
        assert response.status_code == 403 and "X-Lo9i-Client" in response.text


class _Startup:
    def status(self) -> StartupStatus:
        return StartupStatus(enabled=False, managed=False, includes_ollama=False)


async def test_every_json_response_has_a_typed_schema(service):
    """Web clients generate their types from /openapi.json, so no route may answer an untyped object."""
    openapi = create_app(service, RunHub(), _Startup()).openapi()
    untyped = [
        f"{method.upper()} {path}"
        for path, operations in openapi["paths"].items()
        for method, operation in operations.items()
        if not _typed(_json_schema(operation))
    ]
    assert untyped == []


_WEB_SCHEMA = Path(__file__).parents[2] / "clients" / "web" / "openapi.json"


async def test_the_web_clients_schema_matches_the_routes(service):
    """The web client's types are generated from clients/web/openapi.json. Run with UPDATE_OPENAPI=1
    (`npm run api` in clients/web/) to rewrite it after changing a route."""
    current = json.dumps(create_app(service, RunHub(), _Startup()).openapi(), indent=2) + "\n"
    if os.environ.get("UPDATE_OPENAPI"):
        _WEB_SCHEMA.write_text(current)
    assert _WEB_SCHEMA.read_text() == current, (
        "clients/web/openapi.json is out of date: run `npm run api` in clients/web/"
    )


def _json_schema(operation: dict) -> dict:
    """The 200 response's JSON schema. Event streams and audio aren't JSON and count as typed."""
    content = operation["responses"]["200"]["content"]
    return content["application/json"]["schema"] if "application/json" in content else {"$ref": "not JSON"}


def _typed(schema: dict) -> bool:
    if schema.get("type") == "array":
        return _typed(schema["items"])
    return "$ref" in schema or bool(schema.get("properties"))


async def test_send_with_attachment_approve_and_resume(client, script):
    script.call("bash", command="cat notes.txt || true").reply("read it")
    script.call("bash", command="rm -rf build").reply("left it")
    session = await _new_session(client)
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
    assert await client.new_thread("owner") != await client.new_thread("owner")
    assert (await client.memory.snapshot()).facts == []
    assert await client.clients.list() == []
    assert await client.email.accounts() == []
    assert not (await client.telegram.status()).connected
    with pytest.raises(InvalidTokenError):
        await client.telegram.connect("bad")


async def test_speech_routes(client):
    assert (await client.speech.settings()).model in (await client.speech.settings()).models
    assert (await client.speech.change("tiny", ["es"])).languages == ["es"]
    with pytest.raises(SpeechSettingsError):
        await client.speech.change("tiny", ["xx"])
    assert any(v.id == "ef_dora" for v in (await client.speech.settings()).voice_options)


async def test_slack_routes(client):
    assert not (await client.slack.status()).connected
    assert '"socket_mode_enabled": true' in await client.slack.manifest()
    with pytest.raises(SlackError, match="should start with xapp-"):
        await client.slack.connect("bad", "xoxb-1", "xoxp-1")
    await client.slack.disconnect()


async def test_a_client_moving_on_leaves_its_conversation_to_be_archived(client, service, digests):
    session = await _new_session(client)
    for text in ["remember the dentist", "and I use LangGraph"]:
        await collect(client.send(session, text))
    await client.new_thread("owner")
    await asyncio.gather(*service._background)
    assert len(digests.inputs) == 1 and "LangGraph" in digests.inputs[0].transcript
    await client.resume_thread("owner", session.thread_id)
    await collect(client.send(session, "one more"))
    await asyncio.gather(*service._background)
    assert len(digests.inputs) == 1  # still on it


async def _new_session(client: DaemonClient) -> Session:
    return Session("owner", "cli", await client.new_thread("owner"))


async def test_unknown_run_is_404(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.get("/runs/nope/events")).status_code == 404


async def test_skills_and_usage_endpoints(client, script, isolated_settings, monkeypatch):
    from assistant.core.agent import SkillError
    from assistant.core.config import settings
    from assistant.core.skills import store as skills

    monkeypatch.setattr(settings, "skills_dir", str(isolated_settings / "skills"))
    skills.save("news-digest", "Daily news", "1. Search")
    script.call("use_skill", name="news-digest").reply("done")
    await collect(client.send(await _new_session(client), "go"))
    assert [s.name for s in await client.skills.list()] == ["news-digest"]  # built-in ones aren't listed
    assert (await client.skills.get("news-digest")).instructions == "1. Search"
    report = await client.usage.report(7)
    assert report.skills[0].name == "news-digest" and report.tools[0].name == "use_skill"
    await client.skills.delete("news-digest")
    with pytest.raises(SkillError):
        await client.skills.get("news-digest")


async def test_skills_and_servers_are_installed_from_a_repository_and_updated(client, isolated_settings, monkeypatch):
    import shutil

    from assistant.core.agent import McpServerError, RepositoryError, ServerValues, SkillError
    from assistant.core.repositories import checkout

    remote = isolated_settings / "remote"
    (remote / "skills" / "expenses" / "scripts").mkdir(parents=True)
    (remote / "skills" / "expenses" / "SKILL.md").write_text("---\nname: expenses\ndescription: Track\n---\n\nRun it")
    (remote / "skills" / "expenses" / "scripts" / "add.py").write_text("print(1)")
    (remote / "mcp" / "tasks").mkdir(parents=True)
    (remote / "mcp" / "tasks" / "server.yaml").write_text(
        "url: https://tasks.example.com/mcp\nfields: [{key: Authorization, label: Token, secret: true}]"
    )

    async def fetch(url: str, dest: Path) -> str:
        shutil.copytree(remote, dest)
        return "c1"

    async def latest_commit(url: str) -> str:
        return "c1"

    monkeypatch.setattr(checkout, "_fetch", fetch)
    monkeypatch.setattr(checkout, "latest_commit", latest_commit)
    url = "https://example.com/me/extras.git"
    contents = await client.repositories.browse(url)
    assert [s.name for s in contents.skills] == ["expenses"] and contents.servers[0].fields[0].secret
    installed = await client.repositories.install(["expenses"], [ServerValues("tasks", {"Authorization": "t"})], url)
    assert (installed.skills[0].files, installed.servers[0].header_keys) == (["scripts/add.py"], ["Authorization"])
    assert (await client.skills.update_installed("expenses")).source == url
    assert (await client.mcp.update_from_repository("tasks")).source == url
    with pytest.raises(RepositoryError, match="https://"):
        await client.repositories.browse("file:///tmp")
    with pytest.raises(SkillError, match="No skill"):
        await client.skills.update_installed("missing")
    with pytest.raises(McpServerError, match="No MCP server"):
        await client.mcp.update_from_repository("missing")


async def test_plugin_update_routes(client):
    assert await client.repositories.updates() == []  # the extras were never read
    assert await client.repositories.update_checks()
    assert not await client.repositories.set_update_checks(False)
    assert not await client.repositories.update_checks()


async def test_rename_the_assistant(client):
    assert await client.identity.name() == ""
    assert await client.identity.rename("  Max   Power ") == "Max Power"
    assert await client.identity.name() == "Max Power"
    with pytest.raises(InvalidNameError):
        await client.identity.rename("x" * 65)


async def test_cancel_stops_the_conversations_run(client, script, tmp_path):
    script.call("bash", command="echo started > mark; sleep 30")
    session = await _new_session(client)
    run = asyncio.create_task(collect(client.send(session, "wait")))
    await written(tmp_path / "workspace" / "mark")
    assert await client.cancel(session)
    assert isinstance((await asyncio.wait_for(run, 10))[-1], Cancelled)
    assert not await client.cancel(session)


async def test_mcp_servers_through_the_client(client, service, monkeypatch):
    from mcp import Client
    from mcp.server import MCPServer

    from assistant.core.agent import McpServer, McpServerChanges, McpServerError

    fake = MCPServer("notes")

    @fake.tool()
    def add_note(text: str) -> str:
        """Add a note."""
        return text

    monkeypatch.setattr(service.mcp, "_factory", lambda server, handler: Client(fake, message_handler=handler))
    server = McpServer(name="notes", command="notes-server", env={"TOKEN": "secret"})
    assert [t.name for t in await client.mcp.probe(server)] == ["add_note"]
    added = await client.mcp.add(server)
    assert added.env_keys == ["TOKEN"] and added.status == "off"  # the hub isn't running here
    changed = await client.mcp.change("notes", McpServerChanges(trusted=True, include=["add_note"]))
    assert changed.trusted and changed.include == ["add_note"]
    assert [s.name for s in await client.mcp.servers()] == ["notes"]
    await client.mcp.remove("notes")
    with pytest.raises(McpServerError):
        await client.mcp.remove("notes")


async def test_the_model_through_the_client(client, monkeypatch):
    from langchain_core.messages import AIMessage

    import assistant.core.agent.model as model_module
    from assistant.core.agent import ModelSettingsError

    class _Answers:
        async def ainvoke(self, messages, config=None):
            return AIMessage("OK")

    monkeypatch.setattr(model_module, "build_llm", lambda choice, model: _Answers())
    providers = {p.id: p for p in await client.model.providers()}
    assert list(providers)[:3] == ["anthropic", "copilot", "openai"] and "google_genai" in providers
    assert [f.key for f in providers["bedrock_converse"].fields] == [
        "region_name",
        "aws_access_key_id",
        "aws_secret_access_key",
    ]
    status = await client.model.set("copilot", {"api_key": "gh-token"}, "claude-opus-5.5", "claude-sonnet-5.5")
    assert status.source == "app" and status.secrets_set == ["api_key"] and status.model == "claude-opus-5.5"
    with pytest.raises(ModelSettingsError):
        await client.model.set("nope", {"api_key": "k"}, "m", "m")
    assert (await client.model.reset()).source == "env"


async def test_a_conversation_a_client_is_on_cant_be_deleted(client, service):
    from assistant.core.agent import ConversationError

    session = await _new_session(client)
    await collect(client.send(session, "hello"))
    with pytest.raises(ConversationError, match="You're on this conversation"):
        await client.conversations.delete(session.thread_id)
    await client.new_thread("owner")
    await client.conversations.delete(session.thread_id)
    assert [c.thread_id for c in await client.conversations.recent()] == []
    with pytest.raises(ConversationError, match="No conversation"):
        await client.conversations.delete(session.thread_id)


async def test_token_usage_through_the_client(client, script):
    script.reply("hi", usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55})
    await collect(client.send(await _new_session(client), "hello"))
    report = await client.usage.tokens(7)
    assert report.total.calls == 1 and report.total.input_tokens == 50 and report.by_purpose[0].name == "reply"
