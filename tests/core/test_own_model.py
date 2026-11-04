"""A conversation's own model: its replies are written with it instead of the main model, and changing it in a
conversation with messages leaves a note there and gives the model it changed to a summary of them instead."""

import pytest

from lo9i.core import graph as graph_module
from lo9i.core.agent import ConversationBusyError, ModelChangeError, Session
from lo9i.core.agent import own_model as own_model_mixin
from lo9i.core.conversation import own_model
from lo9i.core.conversation.own_model import OwnModel
from lo9i.core.events import ApprovalRequired
from lo9i.core.llm.listing import ModelOption
from tests.conftest import collect

_MAIN = "claude-opus-5-5"
_OFFERED = [ModelOption(_MAIN, "Opus"), ModelOption("fast-1", "Fast One"), ModelOption("deep-2", "Deep Two")]


@pytest.fixture
def built(monkeypatch, script) -> list[str]:
    """The models replies were written with, by id, as the graph built them."""
    ids: list[str] = []

    def build(choice, model):
        ids.append(model)
        return script.model()

    monkeypatch.setattr(graph_module, "build_llm", build)
    return ids


@pytest.fixture
def offered(monkeypatch):
    async def available(provider, values):
        return _OFFERED

    monkeypatch.setattr(own_model_mixin, "available", available)


async def _new(service) -> Session:
    return Session("owner", "cli", await service.new_thread("owner"))


async def _say(service, session, text):
    return await collect(service.send(session, text))


# `built` before `service`: the graph is built when the service opens.
async def test_a_conversation_answers_with_its_own_model_and_others_with_the_main_one(built, service, script, offered):
    session, other = await _new(service), await _new(service)
    changed = await service.set_conversation_model("owner", session.thread_id, "fast-1")
    assert (changed.model, changed.name, changed.main) == ("fast-1", "Fast One", False)
    await _say(service, session, "hi")
    await _say(service, other, "hello")
    assert built == [_MAIN, "fast-1"]
    assert (await service.conversation_model("owner", other.thread_id)).main
    # Before its first message: no note, nothing summarized.
    assert [m.role for m in await service.conversation_messages(session.thread_id)] == ["user", "assistant"]


async def test_changing_it_after_messages_leaves_a_note_and_hands_on_a_summary(
    built, service, script, summaries, offered
):
    script.reply("one").reply("two")
    session = await _new(service)
    await _say(service, session, "first question")
    await service.set_conversation_model("owner", session.thread_id, "deep-2")
    shown = await service.conversation_messages(session.thread_id)
    assert [(m.role, m.text) for m in shown][-1] == ("model", "Deep Two")
    await _say(service, session, "second question")
    prompt, *messages = script.requests[-1]
    assert len(messages) == 1 and "second question" in messages[0].text
    assert "first question" in summaries.inputs[-1] and "summary 1" in prompt.content
    assert built[-1] == "deep-2"
    roles = [m.role for m in await service.conversation_messages(session.thread_id)]
    assert roles == ["user", "assistant", "model", "user", "assistant"]


async def test_the_main_model_or_nothing_goes_back_to_it_and_unknown_ones_are_refused(service, script, offered):
    session = await _new(service)
    await service.set_conversation_model("owner", session.thread_id, "fast-1")
    assert (await service.set_conversation_model("owner", session.thread_id, _MAIN)).main
    assert await own_model.load(service._storage.store, "owner", session.thread_id) is None
    with pytest.raises(ModelChangeError):
        await service.set_conversation_model("owner", session.thread_id, "nope")


async def test_back_and_forth_before_a_message_still_hands_on_a_summary(built, service, script, summaries, offered):
    session = await _new(service)
    await _say(service, session, "first")
    await service.set_conversation_model("owner", session.thread_id, "fast-1")
    await service.set_conversation_model("owner", session.thread_id, "")
    await _say(service, session, "second")
    assert len(script.requests[-1]) == 2 and summaries.inputs
    assert built[-1] == _MAIN
    roles = [m.role for m in await service.conversation_messages(session.thread_id)]
    assert roles.count("model") == 2


async def test_not_while_the_run_waits_for_an_answer(service, script, offered):
    script.call("ask_user", question="Which?", options=["a", "b"]).reply("ok")
    session = await _new(service)
    events = await _say(service, session, "go")
    assert any(isinstance(e, ApprovalRequired) for e in events)
    with pytest.raises(ConversationBusyError):
        await service.set_conversation_model("owner", session.thread_id, "fast-1")


async def test_a_model_of_another_provider_is_the_main_one(service, script):
    session = await _new(service)
    await own_model.save(service._storage.store, "owner", session.thread_id, OwnModel("openrouter", "x/y", "Y"))
    assert (await service.conversation_model("owner", session.thread_id)).main


async def test_without_a_list_the_main_and_worker_models_are_offered(service, monkeypatch):
    async def available(provider, values):
        return []

    monkeypatch.setattr(own_model_mixin, "available", available)
    assert [m.id for m in await service.conversation_models()] == [_MAIN]


async def test_deleting_the_conversation_forgets_its_model(service, script, offered):
    session = await _new(service)
    await _say(service, session, "hi")
    await service.set_conversation_model("owner", session.thread_id, "fast-1")
    await service.delete_conversation("owner", session.thread_id)
    assert await own_model.load(service._storage.store, "owner", session.thread_id) is None
