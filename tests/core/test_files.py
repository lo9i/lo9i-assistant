"""The Files list: the files the user sent and the ones tool results brought, newest first, with the
conversation they're in."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core import uploads
from assistant.core.agent import Session
from assistant.core.agent.files import UploadedFile, _searched
from assistant.core.attachments import TOOL_MEDIA_SENDER, Attachment, reference, tool_uploads, user_uploads
from assistant.core.conversation import file_index
from assistant.core.events import Dispatched
from tests.conftest import collect

NOTE = Attachment("notes.txt", "text/plain", b"buy milk")
PNG = Attachment("shot.png", "image/png", b"\x89PNG fake")


async def test_lists_the_files_sent_with_their_conversation(service):
    first = await service.session("owner", "cli")
    await collect(service.send(first, "read this", [NOTE]))
    second = await service.session("owner", "telegram")
    await collect(service.send(second, "look", [PNG]))
    files = await service.list_files("owner")
    assert {(f.name, f.media_type, f.size, f.thread_id, f.tool) for f in files} == {
        ("notes.txt", "text/plain", 8, first.thread_id, ""),
        ("shot.png", "image/png", 9, second.thread_id, ""),
    }
    assert all(f.conversation for f in files)


async def test_a_page_of_the_files_matching_a_search(service):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    await collect(service.send(session, "look", [PNG]))
    newest_first = await service.list_files("owner")
    assert await service.files_page("owner", limit=1) == newest_first[:1]
    assert await service.files_page("owner", offset=1, limit=1) == newest_first[1:]
    assert [f.name for f in await service.files_page("owner", " IMAGE/ ")] == ["shot.png"]
    assert len(await service.files_page("owner", "you")) == 2


def test_a_search_finds_an_mcp_tools_file_by_its_server_and_tool():
    file = UploadedFile(
        "p", "chart.png", "image/png", 1, "2026-10-25T00:00:00+00:00", "t", "Sales", "mcp__charts__draw"
    )
    assert _searched(file) == "chart.png image/png charts: draw sales"


async def test_a_file_in_several_conversations_is_listed_once_with_the_latest(service, dispatch):
    inbox_session = await service.session("owner", "web")
    events = await collect(service.send(inbox_session, "read this", [NOTE]))
    sent_on = next(e for e in events if isinstance(e, Dispatched))
    where = Session("owner", "web", await service.new_thread("owner"))
    await collect(service.send_dispatched(where, sent_on.id))
    [listed] = await service.list_files("owner")
    assert (listed.name, listed.thread_id) == ("notes.txt", where.thread_id)


async def test_files_deleted_from_disk_are_left_out(service):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    [listed] = await service.list_files("owner")
    uploads.absolute(listed.path).unlink()
    assert await service.list_files("owner") == []


def test_files_from_tool_results_arent_the_users():
    call = AIMessage("", tool_calls=[{"id": "t1", "name": "chart", "args": {}}])
    messages = [
        HumanMessage([reference(NOTE), {"type": "text", "text": "chart it"}]),
        call,
        ToolMessage("sales", tool_call_id="t1", name="chart", artifact=[reference(PNG)]),
        HumanMessage([reference(PNG)], name=TOOL_MEDIA_SENDER),
    ]
    assert [r["name"] for r in user_uploads(messages)] == ["notes.txt"]
    assert [(tool, r["name"]) for tool, r in tool_uploads(messages)] == [("chart", "shot.png")]


async def test_deleting_a_conversation_keeps_the_files_another_one_refers_to(service, dispatch):
    inbox_session = await service.session("owner", "web")
    events = await collect(service.send(inbox_session, "read this", [NOTE]))
    sent_on = next(e for e in events if isinstance(e, Dispatched))
    where = Session("owner", "web", await service.new_thread("owner"))
    await collect(service.send_dispatched(where, sent_on.id))
    [listed] = await service.list_files("owner")
    await service.delete_conversation("owner", where.thread_id)
    assert uploads.absolute(listed.path).is_file()
    [left] = await service.list_files("owner")
    assert (left.path, left.thread_id) == (listed.path, inbox_session.thread_id)
    await service.delete_conversation("owner", inbox_session.thread_id)
    assert not uploads.absolute(listed.path).exists()


async def test_pages_read_the_index_kept_when_runs_end_not_the_conversations(service, monkeypatch):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    listed = [f.path for f in await service.list_files("owner")]

    async def unread(thread_id):
        raise AssertionError(f"read {thread_id}'s messages")

    monkeypatch.setattr(service, "_thread_messages", unread)
    assert [f.path for f in await service.files_page("owner", limit=10)] == listed


async def test_a_conversation_with_a_run_in_progress_is_read_from_its_messages(service):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    await service.store.aput(("conversation_files", "owner"), session.thread_id, {"files": []})
    service._run_starts[session.thread_id] = 0
    assert [f.name for f in await service.list_files("owner")] == ["notes.txt"]


async def test_conversations_from_before_the_index_are_indexed_once(service):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    await file_index.forget(service.store, "owner", session.thread_id)
    assert [f.name for f in await service.list_files("owner")] == ["notes.txt"]
    assert await service.fill_file_index("owner") == 1
    assert await service.fill_file_index("owner") == 0
    [indexed] = (await file_index.of_user(service.store, "owner"))[session.thread_id]
    assert (indexed.name, indexed.tool) == ("notes.txt", "")


async def test_a_deleted_conversations_files_leave_the_index(service):
    session = await service.session("owner", "cli")
    await collect(service.send(session, "read this", [NOTE]))
    await service.delete_conversation("owner", session.thread_id)
    assert session.thread_id not in await file_index.of_user(service.store, "owner")
