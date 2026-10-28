"""A model call refused as too large (HTTP 413, or past the context window) is recovered once: the conversation is
compacted to its last turn and its files and long tool results left out, then the call is made again. Refused
again, the run fails with a plain message. Images are sent scaled down, and old ones left out like old tool results."""

import base64
from io import BytesIO
from typing import Any, cast

import httpx2
import openai
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from PIL import Image

from assistant.core import images
from assistant.core.attachments import Attachment, hydrate, reference
from assistant.core.conversation.oversized import ConversationTooLargeError
from assistant.core.conversation.trim import trimmed
from assistant.core.events import Error
from assistant.core.llm.errors import too_large
from tests.conftest import collect

_LONG = "python3 -c \"print('x' * 3000)\""


def _entity_too_large() -> openai.APIStatusError:
    request = httpx2.Request("POST", "https://api.githubcopilot.com/chat/completions")
    return openai.APIStatusError("Request Entity Too Large", response=httpx2.Response(413, request=request), body=None)


def _png(width: int, height: int, noisy: bool = False, mode: str = "RGB") -> bytes:
    image = Image.effect_noise((width, height), 80).convert(mode) if noisy else Image.new(mode, (width, height))
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _blocks(message: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], message.content) if isinstance(message.content, list) else []


def _images(request: list[Any]) -> list[dict[str, Any]]:
    return [block for message in request for block in _blocks(message) if block.get("type") == "image"]


async def _state(service, session) -> dict[str, Any]:
    return (await service._graph.aget_state({"configurable": {"thread_id": session.thread_id}})).values


async def _earlier_turns(service, script, session) -> None:
    """A screenshot, then a long tool result, then a short exchange."""
    shot = Attachment("shot.png", "image/png", _png(200, 100))
    await collect(service.send(session, "look at this", [shot]))
    script.call("bash", command=_LONG).reply("read it")
    await collect(service.send(session, "read the page"))


def test_errors_that_mean_too_large():
    assert too_large(_entity_too_large())
    assert too_large(ContextOverflowError("too many tokens"))
    assert too_large(ValueError("Error code: 400 - {'code': 'model_max_prompt_tokens_exceeded'}"))
    assert not too_large(ValueError("Error code: 400 - invalid tool schema"))
    assert not too_large(RuntimeError("connection reset"))


async def test_a_request_refused_as_too_large_is_compacted_and_made_again(service, script):
    session = await service.session("u", "cli")
    await _earlier_turns(service, script, session)
    script.refuse(_entity_too_large()).reply("here it is")
    events = await collect(service.send(session, "and now?"))
    assert not any(isinstance(e, Error) for e in events)
    refused, retried = script.requests[-2:]
    assert _images(refused) and not _images(retried)
    assert "summary" in cast(SystemMessage, retried[0]).text
    assert [m.text for m in retried[1:] if isinstance(m, HumanMessage)][-1].endswith("and now?")
    state = await _state(service, session)
    assert state["messages"][-1].text == "here it is"
    assert state["epoch_start"] == len(state["messages"]) - 2


async def test_the_current_turns_files_and_long_results_are_left_out_too(service, script):
    session = await service.session("u", "cli")
    shot = Attachment("shot.png", "image/png", _png(200, 100))
    script.call("bash", command=_LONG).refuse(_entity_too_large()).reply("done")
    await collect(service.send(session, "look and read", [shot]))
    retried = script.requests[-1]
    assert not _images(retried)
    assert any("shot.png left out to save space" in m.text for m in retried if isinstance(m, HumanMessage))
    [result] = [m for m in retried if isinstance(m, ToolMessage)]
    assert result.text.startswith("[Left out to save space")


async def test_refused_again_the_run_fails_with_a_plain_message(service, script):
    session = await service.session("u", "cli")
    await _earlier_turns(service, script, session)
    script.refuse(_entity_too_large()).refuse(_entity_too_large())
    events = await collect(service.send(session, "and now?"))
    [error] = [e for e in events if isinstance(e, Error)]
    assert error.message == str(ConversationTooLargeError())
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[-1] == ("error", str(ConversationTooLargeError()))
    await collect(service.send(session, "shorter then"))
    assert script.requests[-1][-1].text.endswith("shorter then")


async def test_other_errors_are_not_retried(service, script):
    session = await service.session("u", "cli")
    script.refuse(RuntimeError("connection reset"))
    events = await collect(service.send(session, "hi"))
    [error] = [e for e in events if isinstance(e, Error)]
    assert error.message == "RuntimeError: connection reset"
    assert len(script.requests) == 1


def test_the_users_old_files_are_left_out_with_where_they_are_saved():
    shot = reference(Attachment("shot.png", "image/png", _png(20, 10)))
    messages = [HumanMessage([shot, {"type": "text", "text": "look"}]), AIMessage("nice"), HumanMessage("thanks")]
    sent = trimmed(messages, 0, 2)
    [note, text] = _blocks(sent[0])
    assert note["text"].startswith("[File shot.png left out to save space; saved at /")
    assert text["text"] == "look"
    assert trimmed(messages, 0, 0) == messages


def test_a_large_image_is_sent_scaled_down():
    shot = reference(Attachment("shot.png", "image/png", _png(3000, 1500)))
    [block] = _images(hydrate([HumanMessage([shot])], True))
    sent = Image.open(BytesIO(base64.b64decode(block["base64"])))
    assert sent.size == (images.MAX_EDGE, images.MAX_EDGE // 2)
    assert block["mime_type"] == "image/png"


def test_an_image_still_too_heavy_is_sent_as_a_jpeg():
    png = _png(1200, 1200, noisy=True, mode="RGBA")
    data, media_type = images.fit(png, "image/png")
    assert media_type == "image/jpeg" and len(data) < len(png)
    assert Image.open(BytesIO(data)).size == (1200, 1200)


def test_small_images_and_files_pillow_cant_read_are_sent_as_they_are():
    small = _png(100, 50)
    assert images.fit(small, "image/png") == (small, "image/png")
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    assert images.fit(svg, "image/svg+xml") == (svg, "image/svg+xml")
