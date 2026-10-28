"""A model call refused as too large (HTTP 413, or past the context window) is recovered once: the conversation is
compacted to its last turn and its files and long tool results left out, then the call is made again. Refused
again, the run fails with a plain message. Images are sent scaled down, and old ones left out like old tool results.
A subagent's or Home section's call is made again with its tool results left out, and a summary or a memory
digest is written in halves."""

import base64
from io import BytesIO
from typing import Any, cast

import httpx2
import openai
import pytest
from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from PIL import Image

from assistant.core import images
from assistant.core.attachments import Attachment, hydrate, reference
from assistant.core.conversation import digest as digest_module
from assistant.core.conversation import summary as summary_module
from assistant.core.conversation.digest import DigestInput, MemoryDigest, build_digester
from assistant.core.conversation.oversized import ConversationTooLargeError, within_size
from assistant.core.conversation.summary import build_summarizer
from assistant.core.conversation.transcript import halves
from assistant.core.conversation.trim import trimmed
from assistant.core.events import Error
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.errors import too_large
from assistant.core.memory.facts import Fact
from assistant.core.memory.profile import Profile
from assistant.core.subagent import TOO_LARGE
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


async def test_a_subagent_refused_as_too_large_goes_on_with_its_results_left_out(service, script):
    script.call("delegate", task="read the page")
    script.call("bash", command=_LONG).refuse(_entity_too_large()).call("bash", command="echo more")
    script.reply("The page is all x.").reply("Done.")
    events = await collect(service.send(await service.session("u", "cli"), "go"))
    assert not any(isinstance(e, Error) for e in events)
    later = script.requests[-2]
    results = [m.text for m in later if isinstance(m, ToolMessage)]
    assert results[0].startswith("[Left out to save space") and results[1] == "exit code: 0\nmore\n"
    final = [m.text for m in script.requests[-1] if isinstance(m, ToolMessage)]
    assert final == ["The page is all x."]


async def test_a_subagent_refused_again_answers_that_it_stopped(service, script):
    script.call("delegate", task="read the page")
    script.call("bash", command=_LONG).refuse(_entity_too_large()).refuse(_entity_too_large())
    script.reply("Done.")
    events = await collect(service.send(await service.session("u", "cli"), "go"))
    assert not any(isinstance(e, Error) for e in events)
    assert [m.text for m in script.requests[-1] if isinstance(m, ToolMessage)] == [TOO_LARGE]


async def test_within_size_raises_other_errors_and_leaves_nothing_more_to_leave_out():
    async def refuse(messages: list[BaseMessage]) -> str:
        raise _entity_too_large()

    with pytest.raises(openai.APIStatusError):
        await within_size(refuse, [HumanMessage("task")], 1)

    async def fail(messages: list[BaseMessage]) -> str:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await within_size(fail, [HumanMessage("task")], 0)


async def test_a_transcript_refused_as_too_large_is_summarized_in_halves(service, script, monkeypatch):
    monkeypatch.setattr(summary_module, "build_llm", lambda choice, model: script.model())
    summarize = build_summarizer(ModelChoice("anthropic", "m", "w"), service._storage.usage)
    first, second = "USER: " + "a" * 3000, "USER: " + "b" * 3000
    script.refuse(_entity_too_large()).reply("about a").reply("about a and b")
    assert await summarize("", f"{first}\n\n{second}") == "about a and b"
    halves_sent = [request[0].text for request in script.requests[1:]]
    assert first in halves_sent[0] and second not in halves_sent[0]
    assert "about a" in halves_sent[1] and second in halves_sent[1] and first not in halves_sent[1]


async def test_a_short_transcript_refused_as_too_large_isnt_split(service, script, monkeypatch):
    monkeypatch.setattr(summary_module, "build_llm", lambda choice, model: script.model())
    summarize = build_summarizer(ModelChoice("anthropic", "m", "w"), service._storage.usage)
    script.refuse(_entity_too_large())
    with pytest.raises(openai.APIStatusError):
        await summarize("", "USER: hi\n\nASSISTANT: hello")


def test_a_transcript_splits_between_messages_nearest_its_middle():
    assert halves("USER: one\n\nASSISTANT: two\n\nUSER: three") == ("USER: one\n\nASSISTANT: two", "USER: three")
    assert halves("abcdef") == ("abc", "def")


class _HalvingModel:
    """Refuses a prompt with both halves of the transcript; digests each half on its own."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> MemoryDigest:
        prompt = messages[0].text
        self.prompts.append(prompt)
        if "a" * 3000 in prompt and "b" * 3000 in prompt:
            raise _entity_too_large()
        first = "a" * 3000 in prompt
        return MemoryDigest(
            episode_summary="talked about a" if first else "talked about b",
            profile=Profile(goals=["run"] if first else ["run", "swim"]),
            new_facts=["likes a", "likes x"] if first else ["likes b"],
            outdated_fact_ids=["f1"] if first else ["found-1"],
        )


async def test_a_digest_refused_as_too_large_is_made_in_halves(monkeypatch):
    model = _HalvingModel()
    monkeypatch.setattr(digest_module, "build_structured", lambda choice, model_name, schema, meter: model)
    digest = build_digester(ModelChoice("anthropic", "m", "w"), cast(Any, None))
    facts = [Fact("f1", "likes c"), Fact("f2", "lives in Rosario")]
    data = DigestInput("met before", Profile(), facts, "USER: " + "a" * 3000 + "\n\nUSER: " + "b" * 3000)
    joined = await digest(data)
    second_prompt = model.prompts[-1]
    assert "met before" in second_prompt and "talked about a" in second_prompt
    assert "[found-0] likes a" in second_prompt and "f1" not in second_prompt and "[f2]" in second_prompt
    assert joined == MemoryDigest(
        episode_summary="talked about a\n\ntalked about b",
        profile=Profile(goals=["run", "swim"]),
        new_facts=["likes a", "likes b"],
        outdated_fact_ids=["f1"],
    )


async def test_a_digest_over_the_limits_is_asked_again_with_the_error(monkeypatch):
    class _Model:
        def __init__(self):
            self.prompts: list[str] = []

        async def ainvoke(self, messages):
            self.prompts.append(messages[0].text)
            if len(self.prompts) == 1:
                Profile(how_to_reply=[str(i) for i in range(9)])
            return MemoryDigest(episode_summary="s", profile=Profile(), new_facts=[], outdated_fact_ids=[])

    model = _Model()
    monkeypatch.setattr(digest_module, "build_structured", lambda choice, model_name, schema, meter: model)
    digest = build_digester(ModelChoice("anthropic", "m", "w"), cast(Any, None))
    result = await digest(DigestInput("", Profile(), [], "USER: hi"))
    assert result.episode_summary == "s"
    assert "rejected" in model.prompts[1] and "too_long" in model.prompts[1]
