"""The Files list: the files the user sent and the ones tool results brought, newest first, with the
conversation they're in."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core import uploads
from assistant.core.attachments import TOOL_MEDIA_SENDER, Attachment, reference, tool_uploads, user_uploads
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
