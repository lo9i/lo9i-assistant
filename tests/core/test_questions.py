"""Questions with options from the agent (ask_user): the run waits like for an approval, and the
picked options reach the model."""

from assistant.core.agent import Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import ApprovalRequired, Done, ToolFinished, is_question
from tests.conftest import collect

_SOURCES = ["Google", "LinkedIn", "GitHub"]


async def _asked(service, script, **args):
    script.call("ask_user", question="Which sources?", options=_SOURCES, **args).reply("ok")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "look me up"))
    return session, next(e for e in events if isinstance(e, ApprovalRequired))


async def test_the_run_waits_and_the_picked_options_reach_the_model(service, script):
    session, asked = await _asked(service, script, multiple=True)
    assert is_question(asked.request)
    assert asked.request == {"kind": "question", "question": "Which sources?", "options": _SOURCES, "multiple": True}
    events = await collect(service.resume(session, {asked.interrupt_id: {"choices": ["GitHub", "Google"]}}))
    assert events[0] == ToolFinished("ask_user", "The user picked: Google; GitHub.")
    assert isinstance(events[-1], Done)


async def test_skipping_or_picking_nothing_is_told_apart(service, script):
    session, asked = await _asked(service, script, multiple=True)
    events = await collect(service.resume(session, {asked.interrupt_id: {"choices": None}}))
    assert events[0] == ToolFinished("ask_user", "The user closed the question without answering.")
    session, asked = await _asked(service, script, multiple=True)
    events = await collect(service.resume(session, {asked.interrupt_id: {"choices": ["Bing"]}}))
    assert events[0] == ToolFinished("ask_user", "The user picked none of the options.")


async def test_bad_options_and_unattended_runs_are_not_asked(service, script):
    script.call("ask_user", question="Which?", options=["a", "a"]).reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "go"))
    assert ToolFinished("ask_user", "Not asked: options must be different and not empty.") in events
    script.call("ask_user", question="Which?", options=["a", "b"]).reply("ok")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    assert any(isinstance(e, ToolFinished) and e.output.startswith("Not asked: nobody is watching") for e in events)
