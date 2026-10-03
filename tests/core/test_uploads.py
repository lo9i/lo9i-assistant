"""Attachments are stored as files; checkpoints keep references that are loaded for each model call."""

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from assistant.core import uploads
from assistant.core.attachments import TOOL_MEDIA_SENDER, Attachment, hydrate, reference, upload_paths
from assistant.core.events import Error
from tests.conftest import collect

PNG = Attachment("shot.png", "image/png", b"\x89PNG fake")
NOTE = Attachment("notes.txt", "text/plain", b"hello notes")


async def _stored_first_message(service, session):
    state = await service._graph.aget_state({"configurable": {"thread_id": session.thread_id}})
    return state.values["messages"][0].content


async def test_checkpoint_keeps_references_not_file_contents(service):
    session = await service.session("u", "cli")
    await collect(service.send(session, "look", [PNG, NOTE]))
    stored = json.dumps(await _stored_first_message(service, session))
    assert "non_standard" in stored and "base64" not in stored and "hello notes" not in stored


async def test_model_gets_file_contents_rendered_the_same_every_turn(service, script):
    session = await service.session("u", "cli")
    await collect(service.send(session, "look", [PNG]))
    await collect(service.send(session, "again"))
    first, second = (json.dumps([m.content for m in r[1:2]]) for r in script.requests[:2])
    assert '"base64"' in first and first == second


async def test_deleted_file_becomes_a_placeholder(service, script):
    session = await service.session("u", "cli")
    await collect(service.send(session, "look", [PNG]))
    reference = (await _stored_first_message(service, session))[1]["value"]["upload"]["path"]
    uploads.absolute(reference).unlink()
    await collect(service.send(session, "again"))
    assert "is no longer available" in json.dumps(script.requests[-1][1].content)


async def test_unsupported_attachment_is_rejected_before_saving(service, isolated_settings):
    events = await collect(
        service.send(await service.session("u", "cli"), "x", [Attachment("a.zip", "application/zip", b"x")])
    )
    assert events == [Error("Unsupported attachment type: application/zip (a.zip)")]
    assert not (isolated_settings / "uploads").exists()


def _after_a_tool_image() -> list[BaseMessage]:
    call = AIMessage("", tool_calls=[{"id": "t1", "name": "chart", "args": {}}])
    result = ToolMessage("sales", tool_call_id="t1", artifact=[reference(PNG)])
    return [HumanMessage("chart it"), call, result]


def _types(message: BaseMessage) -> list[str]:
    return [block["type"] for block in message.content if isinstance(block, dict)]


def test_images_from_tools_stay_in_the_result_where_the_api_takes_them():
    messages = hydrate(_after_a_tool_image(), images_in_tool_results=True)
    assert len(messages) == 3
    assert _types(messages[2]) == ["text", "text", "image"]


def test_images_from_tools_follow_the_results_in_a_user_message_elsewhere():
    messages = hydrate([*_after_a_tool_image(), AIMessage("a rising line")], images_in_tool_results=False)
    tool, media = messages[2], messages[3]
    assert tool.content[1] == {"type": "text", "text": "[shot.png: in the next message]"}
    assert isinstance(media, HumanMessage) and media.name == TOOL_MEDIA_SENDER
    assert _types(media) == ["text", "text", "image"]
    assert isinstance(messages[4], AIMessage)  # before the next reply, never after it
    assert upload_paths(_after_a_tool_image())  # deleted with the conversation
