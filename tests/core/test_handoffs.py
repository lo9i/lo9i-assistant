"""Conversations handed to a plugin's agent: its tool answers instead of the assistant's model, both
messages are kept, and the assistant hears about it when the user hands the conversation back."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from mcp import Client
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from assistant.core.agent import AssistantService, FolderError, HandoffError
from assistant.core.attachments import Attachment
from assistant.core.events import Done, Error, TextDelta, ToolFinished, ToolStarted
from assistant.core.mcp import hub as hub_module
from assistant.core.mcp.servers import McpServer
from assistant.daemon.restart import Restart
from tests.conftest import collect


def _agent_server(asked: list[dict], release: asyncio.Event) -> MCPServer:
    server = MCPServer("claude-code")

    @server.tool()
    async def converse(conversation: str, folder: str, message: str, ctx: Context) -> str:
        asked.append({"conversation": conversation, "folder": folder, "message": message})
        if message == "show your steps":
            await ctx.report_progress(1, message="Read: README.md")
            await ctx.report_progress(2, message="Ran: pytest")
        if message == "break":
            raise ToolError("the agent gave up")
        if message == "work a while":
            await release.wait()
        return f"Done in {folder}: {message}"

    return server


@pytest.fixture
def asked() -> list[dict]:
    return []


@pytest.fixture
def release() -> asyncio.Event:
    """Lets the agent answer \"work a while\"."""
    return asyncio.Event()


@pytest.fixture
async def service(script, digests, summaries, titles, asked, release, monkeypatch) -> AsyncIterator[AssistantService]:
    fake = _agent_server(asked, release)
    monkeypatch.setattr(hub_module, "open_client", lambda server, handler, auth: Client(fake, message_handler=handler))
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        await svc.add_mcp_server(
            McpServer(
                "claude-code", command="x", agent_command="claude", agent_name="Claude Code", agent_tool="converse"
            )
        )
        for _ in range(100):
            if (await svc.mcp_servers())[0].status == "connected":
                break
            await asyncio.sleep(0.02)
        yield svc
        stop.set()
        await task


async def _handed(service, tmp_path):
    session = await service.session("owner", "cli")
    await service.hand_conversation("owner", session.thread_id, "claude", str(tmp_path))
    return session


async def test_the_agent_answers_instead_of_the_assistant_and_both_messages_are_kept(service, script, asked, tmp_path):
    assert [(a.command, a.name) for a in await service.agents()] == [("claude", "Claude Code")]
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "fix the tests"))
    assert isinstance(events[0], ToolStarted) and events[0].name == "Claude Code"
    assert TextDelta(f"Done in {tmp_path}: fix the tests") in events and isinstance(events[-1], Done)
    assert asked == [{"conversation": session.thread_id, "folder": str(tmp_path), "message": "fix the tests"}]
    assert script.requests == []  # the assistant's model wasn't asked
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[-2:] == [("user", "fix the tests"), ("assistant", f"Done in {tmp_path}: fix the tests")]


async def test_the_agents_steps_are_shown_inside_its_call_as_it_works(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "show your steps"))
    call = events[0]
    assert isinstance(call, ToolStarted) and call.id
    steps = [(e.name, e.within) for e in events if isinstance(e, ToolStarted | ToolFinished) and e.within]
    assert steps == [(s, call.id) for s in ("Read: README.md", "Read: README.md", "Ran: pytest", "Ran: pytest")]
    assert isinstance(events[-1], Done)


async def test_handed_back_the_assistant_answers_and_hears_who_did_meanwhile(service, script, tmp_path):
    script.reply("I see Claude Code fixed them.")
    session = await _handed(service, tmp_path)
    await collect(service.send(session, "fix the tests"))
    await service.take_back_conversation("owner", session.thread_id)
    assert await service.conversation_agent("owner", session.thread_id) is None
    await collect(service.send(session, "what happened?"))
    _, *messages = script.requests[-1]
    header = " ".join(b["text"] for b in messages[-1].content if b.get("type") == "text")
    assert "handed this conversation to Claude Code" in header and f"Done in {tmp_path}" in messages[-2].content


async def test_an_agent_error_is_shown_and_nothing_is_added(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "break"))
    assert isinstance(events[-1], Error) and "the agent gave up" in events[-1].message
    assert await service.conversation_messages(session.thread_id) == []


async def test_files_dont_reach_the_agent(service, tmp_path):
    session = await _handed(service, tmp_path)
    photo = Attachment("photo.png", "image/png", b"\x89PNG")
    events = await collect(service.send(session, "look", [photo]))
    assert isinstance(events[-1], Error) and "takes text only" in events[-1].message


async def test_only_an_installed_agent_and_an_existing_folder_can_be_handed_to(service, tmp_path):
    session = await service.session("owner", "cli")
    with pytest.raises(HandoffError, match="No plugin brings /codex"):
        await service.hand_conversation("owner", session.thread_id, "codex", str(tmp_path))
    with pytest.raises(HandoffError, match="isn't an existing folder"):
        await service.hand_conversation("owner", session.thread_id, "claude", str(tmp_path / "missing"))


async def test_a_restart_waits_until_the_agent_has_replied(service, asked, release, tmp_path):
    """The agent may restart the daemon it answers through; stopping it at once would stop the agent."""
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "work a while")))
    for _ in range(100):
        if asked:
            break
        await asyncio.sleep(0.02)
    stop = asyncio.Event()
    restart = Restart(service, stop)
    assert restart.request() == 1
    await asyncio.sleep(0.05)
    assert not stop.is_set()
    release.set()
    assert isinstance((await run)[-1], Done)
    await asyncio.wait_for(stop.wait(), 1)
    assert restart.requested


async def test_with_no_run_in_progress_a_restart_is_at_once(service):
    stop = asyncio.Event()
    restart = Restart(service, stop)
    assert restart.request() == 0
    await asyncio.wait_for(stop.wait(), 1)
    assert restart.requested


async def test_the_workspace_is_created_when_handed_to_and_not_listed_as_recent(service):
    from assistant.core.config import settings

    session = await service.session("owner", "cli")
    workspace = str(Path(settings.agent_workspace_dir))
    handoff = await service.hand_conversation("owner", session.thread_id, "claude", workspace)
    assert handoff.folder == workspace and Path(workspace).is_dir()
    assert (await service.agent_folders("owner")).recent == []


async def test_folders_used_before_are_offered_newest_first_while_they_exist(service, tmp_path):
    first, second, gone = tmp_path / "first", tmp_path / "second", tmp_path / "gone"
    for folder in (first, second, gone):
        folder.mkdir()
    session = await service.session("owner", "cli")
    for folder in (first, gone, second, first):
        await service.hand_conversation("owner", session.thread_id, "claude", str(folder))
    gone.rmdir()
    assert (await service.agent_folders("owner")).recent == [str(first), str(second)]


async def test_browsing_lists_the_folders_inside_without_hidden_ones_or_files(service, tmp_path):
    root = tmp_path / "browsed"
    for name in ("b", "A", ".git"):
        (root / name).mkdir(parents=True)
    (root / "notes.txt").write_text("")
    listing = await service.child_folders(str(root))
    assert listing.children == [str(root / "A"), str(root / "b")]
    assert listing.parent == str(tmp_path)
    assert (await service.child_folders("/")).parent is None
    for wrong in ("relative", str(root / "missing"), str(root / "notes.txt")):
        with pytest.raises(FolderError):
            await service.child_folders(wrong)
