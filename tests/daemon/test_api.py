"""The daemon API through DaemonClient, served in-process (no socket needed)."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core import notifications
from assistant.core.agent import (
    ConversationError,
    HomeSection,
    HomeSectionsError,
    InvalidNameError,
    InvalidSearchKeyError,
    Session,
    ShownStep,
    SpeechSettingsError,
)
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.core.conversation.dispatch_setting import DispatchSetting, DispatchSettingError
from assistant.core.events import ApprovalRequired, Cancelled, Dispatched, Done, ToolFinished
from assistant.core.home import results
from assistant.core.internet import brave_key
from assistant.core.logs import LogWriter, log_sources
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.daemon.shutdown import Ending, Pending
from assistant.protocol import (
    CLIENT_HEADER,
    CLIENT_ID_HEADER,
    Commit,
    NoEndingError,
    PendingEnding,
    StartupStatus,
    StopRefusedError,
    UpdateError,
    UpdateStatus,
)
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


class _Shutdown:
    def __init__(self, refusal: str | None = None) -> None:
        self.requests: list[Ending] = []
        self.askers: list[str] = []
        self._refusal = refusal

    def request(self, ending: Ending, by: str = "") -> int:
        if ending is Ending.STOP and self._refusal:
            raise StopRefusedError(self._refusal)
        self.requests.append(ending)
        self.askers.append(by)
        return 2

    def pending(self) -> Pending | None:
        return Pending(self.requests[-1], 2) if self.requests else None

    def take_back(self, by: str = "") -> None:
        if not self.requests:
            raise NoEndingError("Nothing to take back.")
        self.requests.clear()

    def now(self, by: str = "") -> int:
        if not self.requests:
            raise NoEndingError("Nothing waits.")
        return 2


@asynccontextmanager
async def _system(service, shutdown: _Shutdown):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub(), shutdown=shutdown)))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        yield DaemonClient(http).system


async def test_a_restart_or_stop_is_requested_and_says_how_many_runs_it_waits_for(service):
    shutdown = _Shutdown()
    async with _system(service, shutdown) as system:
        assert (await system.restart()).waiting_for_runs == 2
        assert (await system.stop()).waiting_for_runs == 2
    assert shutdown.requests == [Ending.RESTART, Ending.STOP]
    # The log says who asked (daemon/shutdown.py).
    assert shutdown.askers == ["t (unix socket)"] * 2


async def test_a_pending_restart_is_read_made_to_go_ahead_and_taken_back(service):
    async with _system(service, _Shutdown()) as system:
        assert (await system.ending()).ending == ""
        with pytest.raises(NoEndingError):
            await system.end_now()
        await system.restart()
        assert await system.ending() == PendingEnding("restart", 2)
        assert await system.end_now() == 2
        assert (await system.take_back_ending()).ending == ""
        with pytest.raises(NoEndingError):
            await system.take_back_ending()


async def test_a_stop_the_service_manager_would_undo_is_refused_with_its_reason(service):
    async with _system(service, _Shutdown(refusal="macOS would start it again")) as system:
        with pytest.raises(StopRefusedError, match="macOS would start it again"):
            await system.stop()


class _Updates:
    def __init__(self, refusal: str = "") -> None:
        self.started = 0
        self._refusal = refusal
        self._status = UpdateStatus(
            installed_from="git",
            current=Commit("a1", "First", "2026-10-24T00:00:00Z"),
            upstream="origin/main",
            behind=1,
            new=[Commit("b2", "Second", "2026-10-24T01:00:00Z")],
            checked_at="2026-10-24T02:00:00Z",
            can_update=not refusal,
            reason=refusal,
            state="idle",
            step="",
            error="",
        )

    async def status(self) -> UpdateStatus:
        return self._status

    async def check(self) -> UpdateStatus:
        return self._status

    async def start(self) -> UpdateStatus:
        if self._refusal:
            raise UpdateError(self._refusal)
        self.started += 1
        return replace(self._status, state="updating", step="Downloading the update")


@asynccontextmanager
async def _updating(service, updates: _Updates):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub(), updates=updates)))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        yield DaemonClient(http).system


async def test_the_apps_see_the_version_whats_new_and_start_an_update(service):
    updates = _Updates()
    async with _updating(service, updates) as system:
        status = await system.update_status()
        assert status.current == Commit("a1", "First", "2026-10-24T00:00:00Z")
        assert (await system.check_for_update()).new == [Commit("b2", "Second", "2026-10-24T01:00:00Z")]
        assert (await system.update()).step == "Downloading the update"
    assert updates.started == 1


async def test_an_update_that_cant_be_installed_says_why(service):
    async with _updating(service, _Updates(refusal="This copy has changes that aren't committed.")) as system:
        with pytest.raises(UpdateError, match="changes that aren't committed"):
            await system.update()


async def test_stopping_needs_a_paired_device_on_the_network(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.post("/system/stop")).status_code == 401


async def test_host_describes_the_computer_the_daemon_runs_on(client):
    host = await client.system.host()
    assert host.hostname and host.cpu_cores > 0 and 0 <= host.cpu_percent <= 100
    assert 0 < host.memory_used <= host.memory_total and 0 < host.disk_used <= host.disk_total
    assert host.uptime_seconds > 0 and host.version


async def test_every_json_response_has_a_typed_schema(service):
    """Web clients generate their types from /openapi.json, so no route may answer an untyped object."""
    openapi = create_app(
        service, RunHub(), _Startup(), _Shutdown(), logs=log_sources(LogWriter()), updates=_Updates()
    ).openapi()
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
    current = (
        json.dumps(
            create_app(
                service, RunHub(), _Startup(), _Shutdown(), logs=log_sources(LogWriter()), updates=_Updates()
            ).openapi(),
            indent=2,
        )
        + "\n"
    )
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


async def test_clients_go_to_the_inbox_and_new_starts_a_conversation(client, service):
    inbox = await client.inbox_thread("owner")
    assert inbox == await service.inbox_thread("owner") == await client.inbox_thread("owner")
    assert await client.new_thread("owner") != inbox


async def test_send_with_attachment_approve_and_resume(client, script):
    script.call("bash", command="cat notes.txt || true").reply("read it")
    script.call("bash", command="rm -rf build").reply("left it")
    session = await _new_session(client)
    events = await collect(client.send(session, "read it", [Attachment("notes.txt", "text/plain", b"hi")]))
    assert isinstance(events[1], ToolFinished) and isinstance(events[-1], Done)

    events = await collect(client.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert await client.conversations.pending_approvals(session.thread_id) == [approval]
    events = await collect(client.resume(session, {approval.interrupt_id: {"approved": False, "reason": "no"}}))
    assert events[0] == ToolFinished("bash", "The user rejected this (no).")
    assert await client.conversations.pending_approvals(session.thread_id) == []


async def test_the_inbox_sends_a_message_on_and_the_client_sends_it_where_it_went(dispatch, client, script):
    inbox = Session("owner", "web", await client.inbox_thread("owner"))
    [sent] = [e for e in await collect(client.send(inbox, "plan my week")) if isinstance(e, Dispatched)]
    assert sent.thread_id == "" and sent.text == "plan my week"
    side = await _new_session(client)
    script.reply("A plan.")
    events = await collect(client.send_dispatched(side, sent.id, sent.text))
    assert isinstance(events[-1], Done)
    events = await collect(client.move_dispatched(inbox))
    [asked] = [e for e in events if isinstance(e, ApprovalRequired)]
    assert asked.request["options"] == ["A new conversation"]
    assert await client.model.dispatch() == DispatchSetting()
    assert await client.model.set_dispatch(DispatchSetting(0.5)) == DispatchSetting(0.5)
    with pytest.raises(DispatchSettingError):
        await client.model.set_dispatch(DispatchSetting(2))


async def test_home_is_shown_refreshed_and_its_sections_edited(client, service):
    assert [c.section.title for c in (await client.home.get()).cards] == ["Calendario", "Watchlist", "Gastos"]
    with pytest.raises(HomeSectionsError, match="Every section needs a title"):
        await client.home.save_sections([HomeSection(title="", prompt="x")])
    page = await client.home.save_sections([HomeSection(title="Agenda", prompt="Today.", plugins=["calendar"])])
    assert [c.section.title for c in page.cards] == ["Agenda"] and page.cards[0].section.id
    await service.home_refresh.wait("owner")
    await client.home.refresh(force=True)
    await service.home_refresh.wait("owner")
    page = await client.home.get()
    assert page.updated_at and page.cards[0].result is not None and page.cards[0].result.status == "unavailable"
    assert len((await client.home.reset_sections()).cards) == 3


async def test_a_client_showing_home_keeps_it_current_until_it_stops(client, service):
    # Midday, so the last refresh 31 minutes before is the same day: just after midnight it would be yesterday's,
    # and the day's first tick refreshes whoever watches.
    now = datetime.now(ZoneInfo(settings.timezone)).replace(hour=12, minute=0, second=0, microsecond=0)
    await results.mark_refreshed(service.store, "owner", now - timedelta(minutes=31))
    await client.home.watch()
    await service.home_schedule.tick(now)
    assert (await client.home.get()).refreshing
    await service.home_refresh.wait("owner")
    await results.mark_refreshed(service.store, "owner", now - timedelta(minutes=31))
    await client.home.unwatch()
    await service.home_schedule.tick(now)
    assert not (await client.home.get()).refreshing


async def test_notifications_are_listed_read_and_dismissed(client, service):
    first = await notifications.add(service.store, "owner", "job", "Job news", "Read the news.", True)
    await notifications.add(service.store, "owner", "background", "Trip", "⚠️ It failed.", False, "owner:t1")
    listed = await client.notifications.list()
    assert [(n.title, n.thread_id, n.read) for n in listed] == [("Trip", "owner:t1", False), ("Job news", "", False)]
    await client.notifications.mark_read()
    assert all(n.read for n in await client.notifications.list())
    await client.notifications.dismiss(first.id)
    assert [n.title for n in await client.notifications.list()] == ["Trip"]
    await client.notifications.clear()
    assert await client.notifications.list() == []


async def test_a_job_runs_reply_is_read_and_a_missing_run_is_a_job_error(client, service):
    from assistant.core.jobs import store
    from assistant.core.jobs.store import Job, JobError, RunRecord

    at = "2026-10-24T09:00:00+00:00"
    job = Job("news", "owner", "0 9 * * *", "UTC", "Read the news.", at)
    job.record(RunRecord(at, "skipped", "the previous run was still going"))
    await store.save(service.store, job)
    assert await client.jobs.run_reply("news", at) == "the previous run was still going"
    with pytest.raises(JobError):
        await client.jobs.run_reply("news", "2026-10-23T09:00:00+00:00")


async def test_threads_memory_and_channels(client):
    assert await client.new_thread("owner") != await client.new_thread("owner")
    assert (await client.memory.snapshot()).facts == []
    assert (await client.memory.set_profile_section("interests", ["chess"])).profile == {"interests": ["chess"]}
    assert await client.clients.list() == []
    assert await client.email.accounts() == []
    assert await client.email.set_recipients(["Friend@Test.com"]) == ["friend@test.com"]
    assert await client.email.recipients() == ["friend@test.com"]
    assert await client.channels.list() == []


async def test_speech_routes(client):
    assert (await client.speech.settings()).model in (await client.speech.settings()).models
    assert (await client.speech.change("tiny", ["es"])).languages == ["es"]
    with pytest.raises(SpeechSettingsError):
        await client.speech.change("tiny", ["xx"])
    assert any(v.id == "ef_dora" for v in (await client.speech.settings()).voice_options)


async def test_web_search_routes(client, monkeypatch):
    async def check(key):
        if key != "good":
            raise InvalidSearchKeyError("Brave didn't accept the key: 401")

    monkeypatch.setattr(brave_key, "check", check)
    assert not (await client.web_search.status()).brave_key_set
    with pytest.raises(InvalidSearchKeyError, match="401"):
        await client.web_search.set_brave_key("bad")
    assert (await client.web_search.set_brave_key(" good ")).brave_key_set
    assert (await client.web_search.status()).brave_key_set
    assert not (await client.web_search.remove_brave_key()).brave_key_set


async def test_a_client_moving_on_leaves_its_conversation_to_be_archived(client, service, digests):
    session = await _new_session(client)
    for text in ["remember the dentist", "and I use LangGraph"]:
        await collect(client.send(session, text))
    await client.new_thread("owner")
    await asyncio.gather(*service._background)
    await service.memory_writer.write_all()
    assert len(digests.inputs) == 1 and "LangGraph" in digests.inputs[0].transcript
    await client.resume_thread("owner", session.thread_id)
    await collect(client.send(session, "one more"))
    await asyncio.gather(*service._background)
    await service.memory_writer.write_all()
    assert len(digests.inputs) == 1  # still on it


async def _new_session(client: DaemonClient) -> Session:
    return Session("owner", "cli", await client.new_thread("owner"))


async def test_unknown_run_is_404(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.get("/runs/nope/events")).status_code == 404


async def test_a_conversation_opens_with_its_messages_and_the_runs_in_progress_there(service, script):
    script.reply("Hello.")
    hub = RunHub()
    session = Session("owner", "cli", await service.new_thread("owner"))
    await collect(service.send(session, "hi"))
    release = asyncio.Event()

    async def waiting():
        await release.wait()
        yield Done()

    run = hub.start(session.thread_id, waiting(), channel="telegram", text="and now?")
    hub.start("elsewhere", waiting())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(create_app(service, hub))),
        base_url="http://127.0.0.1",
        headers={CLIENT_HEADER: "t"},
    ) as http:
        live = (await http.get(f"/conversations/{session.thread_id}/live")).json()
        opened = await DaemonClient(http).conversations.live(session.thread_id)  # as the terminal app opens it
    release.set()
    assert [m.text for m in opened.messages] == ["hi", "Hello."] and opened.runs == live["runs"]
    assert [m["text"] for m in live["messages"]] == ["hi", "Hello."]
    assert live["runs"] == [
        {
            "run_id": run.id,
            "thread_id": session.thread_id,
            "channel": "telegram",
            "client_id": "",
            "text": "and now?",
            "notice": "",
        }
    ]


async def test_a_profile_edit_with_an_unknown_section_or_too_many_items_is_422(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.put("/memory/profile/hobbies", json={"items": ["chess"]})).status_code == 422
        too_many = {"items": [f"goal {i}" for i in range(9)]}
        assert (await http.put("/memory/profile/goals", json=too_many)).status_code == 422


async def test_a_message_to_the_agent_with_neither_text_nor_files_is_400(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        response = await http.post("/conversations/t/agent/messages", data={"text": "  "})
        assert response.status_code == 400 and "attach a file" in response.text


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


async def test_a_conversation_is_handed_to_an_agent_and_back(client, service, tmp_path):
    from assistant.core.agent import HandoffError
    from assistant.core.mcp.servers import McpServer

    await service.add_mcp_server(
        McpServer(
            "coder",
            agent_command="claude",
            agent_name="Claude Code",
            agent_worker="/usr/bin/true",
        )
    )
    assert [a.command for a in await client.conversations.agents()] == ["claude"]
    thread_id = (await _new_session(client)).thread_id
    assert await client.conversations.agent(thread_id) is None
    handoff = await client.conversations.hand_to(thread_id, "claude", str(tmp_path))
    assert (handoff.name, handoff.folder) == ("Claude Code", str(tmp_path))
    assert await client.conversations.agent(thread_id) == handoff
    with pytest.raises(HandoffError):
        await client.conversations.hand_to(thread_id, "claude", "relative/folder")
    with pytest.raises(HandoffError, match="isn't working on anything now"):
        await client.conversations.message_agent(thread_id, "skip the slow tests")
    with pytest.raises(HandoffError, match="isn't working on anything now"):
        await client.conversations.message_agent(thread_id, "", [Attachment("shot.png", "image/png", b"png")])
    with pytest.raises(HandoffError, match="isn't working on anything now"):
        await client.conversations.interrupt_agent(thread_id)
    await client.conversations.take_back(thread_id)
    assert await client.conversations.agent(thread_id) is None
    assert (await client.conversations.agent_folders()).recent == [str(tmp_path)]


async def test_the_folders_inside_one_are_listed_to_browse_to(client, tmp_path):
    from assistant.core.agent import FolderError

    root = tmp_path / "browsed"
    (root / "project").mkdir(parents=True)
    listing = await client.conversations.child_folders(str(root))
    assert (listing.path, listing.children) == (str(root), [str(root / "project")])
    with pytest.raises(FolderError):
        await client.conversations.child_folders("relative")


async def test_facts_and_episodes_are_edited_and_deleted(client, service):
    from assistant.core.agent import MemoryEditError, MemoryNotFoundError
    from assistant.core.config import settings
    from assistant.core.memory import episodes, facts
    from assistant.core.memory.episodes import Episode

    fact_id = await facts.add(service.store, settings.owner_id, "likes jazz")
    await episodes.save(service.store, settings.owner_id, Episode("2026-10-01T09:00", "2026-10-01T10:00", "A trip"))
    edited = await client.memory.edit_fact(fact_id, "likes jazz and blues")
    assert [f.text for f in await client.memory.facts()] == ["likes jazz and blues"]
    with pytest.raises(MemoryEditError):
        await client.memory.edit_fact(edited.id, " ")
    await client.memory.delete_fact(edited.id)
    with pytest.raises(MemoryNotFoundError):
        await client.memory.delete_fact(edited.id)
    episode = (await client.memory.episodes())[0]
    assert (await client.memory.edit_episode(episode.id, "A trip to Rome")).summary == "A trip to Rome"
    await client.memory.delete_episode((await client.memory.episodes())[0].id)
    assert await client.memory.facts() == [] and await client.memory.episodes() == []


async def test_skills_are_pinned_to_a_conversation(client, isolated_settings, monkeypatch):
    from assistant.core.agent import SkillError
    from assistant.core.config import settings
    from assistant.core.skills import store as skills

    monkeypatch.setattr(settings, "skills_dir", str(isolated_settings / "skills"))
    skills.save("coding", "Programming help", "Run the tests.")
    thread_id = (await _new_session(client)).thread_id
    assert await client.conversations.pin(thread_id, "coding") == ["coding"]
    assert await client.conversations.pinned(thread_id) == ["coding"]
    with pytest.raises(SkillError):
        await client.conversations.pin(thread_id, "nope")
    assert await client.conversations.unpin(thread_id, "coding") == []


async def test_skills_and_servers_are_installed_from_a_repository_and_updated(client, isolated_settings, monkeypatch):
    import shutil

    from assistant.core.agent import McpServerError, RepositoryError, ServerValues, SkillError
    from assistant.core.repositories import checkout

    remote = isolated_settings / "remote"
    (remote / "other" / "general" / "expenses" / "scripts").mkdir(parents=True)
    (remote / "other" / "general" / "expenses" / "SKILL.md").write_text(
        "---\nname: expenses\ndescription: Track\n---\n\nRun it"
    )
    (remote / "other" / "general" / "expenses" / "scripts" / "add.py").write_text("print(1)")
    (remote / "other" / "general" / "tasks").mkdir(parents=True)
    (remote / "other" / "general" / "tasks" / "server.yaml").write_text(
        "url: https://tasks.example.com/mcp\nfields: [{key: Authorization, label: Token, secret: true}]"
    )

    async def fetch(url: str, dest: Path, token: str = "") -> str:
        shutil.copytree(remote, dest)
        return "c1"

    async def latest_commit(url: str, token: str = "") -> str:
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


async def test_repositories_are_added_listed_and_removed(client, monkeypatch):
    from assistant.core.agent import RepositoryError
    from assistant.core.repositories import contents

    async def browse(store, url, token=""):
        if "broken" in url:
            raise RepositoryError("Couldn't get the repository: not found")
        return contents.RepositoryContents([], [])

    monkeypatch.setattr(contents, "browse", browse)
    mine = "https://github.com/me/plugins"
    assert [(r.name, r.official) for r in await client.repositories.list()] == [("lo9i/lo9i-assistant-extras", True)]
    assert (await client.repositories.add(mine)).official is False
    with pytest.raises(RepositoryError, match="not found"):
        await client.repositories.add("https://github.com/me/broken")
    read = await client.repositories.plugins()
    assert [(r.repository.name, r.contents is not None, r.error) for r in read] == [
        ("lo9i/lo9i-assistant-extras", True, ""),
        ("me/plugins", True, ""),
    ]
    with pytest.raises(RepositoryError, match="built in"):
        await client.repositories.remove(read[0].repository.url)
    await client.repositories.remove(mine)
    assert len(await client.repositories.list()) == 1


async def test_plugin_update_routes(client):
    assert await client.repositories.updates() == []  # the extras were never read
    assert await client.repositories.update_checks()
    assert not await client.repositories.set_update_checks(False)
    assert not await client.repositories.update_checks()


async def test_prompt_texts_are_listed_edited_and_reset(client):
    from assistant.core.agent import PromptEditError, UnknownPromptError

    listed = await client.prompts.list()
    assert [s.name for s in listed] == ["persona", "operating", "channels"]
    assert not any(s.edited for s in listed)
    saved = await client.prompts.save("persona", "You are Lo9i.")
    assert saved.text == "You are Lo9i." and saved.edited and saved.default != saved.text
    reset = await client.prompts.reset("persona")
    assert reset.text == reset.default and not reset.edited
    with pytest.raises(PromptEditError):
        await client.prompts.save("persona", " ")
    with pytest.raises(UnknownPromptError):
        await client.prompts.save("title", "x")
    with pytest.raises(UnknownPromptError):
        await client.prompts.reset("title")


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


async def test_mcp_servers_through_the_client(client, service, monkeypatch, isolated_settings):
    from mcp import Client
    from mcp.server import MCPServer

    from assistant.core.agent import McpServer, McpServerChanges, McpServerError

    fake = MCPServer("notes")

    @fake.tool()
    def add_note(text: str) -> str:
        """Add a note."""
        return text

    monkeypatch.setattr(
        service.mcp, "_factory", lambda server, handler, auth, extensions: Client(fake, message_handler=handler)
    )
    server = McpServer(name="notes", command="notes-server", env={"TOKEN": "secret"})
    assert [t.name for t in (await client.mcp.probe(server)).tools] == ["add_note"]
    added = await client.mcp.add(server)
    assert added.env_keys == ["TOKEN"] and added.status == "off"  # the hub isn't running here
    changed = await client.mcp.change("notes", McpServerChanges(trusted=True, include=["add_note"]))
    assert changed.trusted and changed.include == ["add_note"]
    assert [s.name for s in await client.mcp.servers()] == ["notes"]
    data = isolated_settings / "data" / "notes"
    data.mkdir(parents=True)
    await client.mcp.remove("notes", delete_data=True)
    assert not data.exists()
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


async def test_files_through_the_client(client):
    from assistant.core.attachments import Attachment

    session = await _new_session(client)
    await collect(client.send(session, "read this", [Attachment("notes.txt", "text/plain", b"buy milk")]))
    [listed] = await client.files.list()
    assert (listed.name, listed.size, listed.thread_id) == ("notes.txt", 8, session.thread_id)
    assert await client.files.content(listed) == b"buy milk"
    from dataclasses import replace

    from assistant.core.agent import FileUnavailableError

    with pytest.raises(FileUnavailableError):
        await client.files.content(replace(listed, path="../../lo9i.db"))


async def test_token_usage_through_the_client(client, script):
    script.reply("hi", usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55})
    await collect(client.send(await _new_session(client), "hello"))
    report = await client.usage.tokens(7)
    assert report.total.calls == 1 and report.total.input_tokens == 50 and report.by_purpose[0].name == "reply"


async def test_conversation_stats_through_the_client(client, script):
    session = await _new_session(client)
    assert (await client.conversations.stats(session.thread_id)).messages == 0
    script.reply("hi", usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55})
    await collect(client.send(session, "hello"))
    stats = await client.conversations.stats(session.thread_id)
    assert stats.thread_id == session.thread_id and stats.messages == 2 and stats.model_calls == 1
    assert stats.input_tokens == 50 and stats.output_tokens == 5 and stats.last_activity is not None


async def test_a_delegate_calls_steps_reach_the_client_with_the_conversation(client, service, script):
    script.call("delegate", task="look").call("bash", command="echo hi").reply("hi").reply("ok")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "go"))
    call = next(m for m in await client.conversations.messages(session.thread_id) if m.role == "tool")
    assert call.steps == [ShownStep("bash", {"command": "echo hi"}, "exit code: 0\nhi\n")]


async def test_a_tool_calls_preview_loads_in_full_through_the_client(client, service, script):
    script.call("bash", command="seq 1 100").reply("Counted.")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "count"))
    call = next(m for m in await client.conversations.messages(session.thread_id) if m.role == "tool")
    assert call.partial and call.detail == "seq 1 100"
    whole = await client.conversations.tool_call(session.thread_id, call.call_id)
    assert whole.args == {"command": "seq 1 100"} and "\n100\n" in whole.output
    with pytest.raises(ConversationError):
        await client.conversations.tool_call(session.thread_id, "no/such call")


async def test_a_step_inside_a_delegate_call_loads_in_full_through_the_client(client, service, script):
    script.call("delegate", task="count").call("bash", command="seq 1 100").reply("Counted.").reply("ok")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "go"))
    call = next(m for m in await client.conversations.messages(session.thread_id) if m.role == "tool")
    assert call.steps[0].partial and "\n100\n" not in call.steps[0].output
    whole = await client.conversations.tool_call_step(session.thread_id, call.call_id, 0)
    assert whole.args == {"command": "seq 1 100"} and "\n100\n" in whole.output
    with pytest.raises(ConversationError):
        await client.conversations.tool_call_step(session.thread_id, call.call_id, 1)


async def test_kept_keys_are_listed_and_deleted_through_the_client(client, service):
    from assistant.core.agent import KeptKeys
    from assistant.core.mcp import keys

    await keys.put(service.store, service.secrets, "hello", keys.Keys({"HELLO_TOKEN": "s3cret"}))
    assert await client.repositories.kept_keys() == [KeptKeys("hello", ["HELLO_TOKEN"])]
    await client.repositories.forget_keys(KeptKeys("hello", ["HELLO_TOKEN"]))
    assert await client.repositories.kept_keys() == []
