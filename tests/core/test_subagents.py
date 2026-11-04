"""Subagents (delegate): a task worked on with a fresh context, whose answer alone reaches the
conversation; approvals inside it pause the run and resume it where it stopped."""

from langchain_core.messages import HumanMessage, ToolMessage

from lo9i.core import subagent_steps
from lo9i.core.agent import Session, ShownStep
from lo9i.core.config import settings
from lo9i.core.context import UNATTENDED_CHANNEL
from lo9i.core.events import ApprovalRequired, Done, ToolFinished, ToolStarted
from lo9i.core.subagent import LIMIT_REACHED
from tests.conftest import collect


def _tool_results(messages) -> list[str]:
    return [m.text for m in messages if isinstance(m, ToolMessage)]


async def test_only_the_answer_reaches_the_conversation(service, script):
    script.call("delegate", task="Find the token")
    script.call("bash", command="echo token-in-a-long-log").reply("The token is 42.")
    script.reply("It's 42.")
    events = await collect(service.send(await service.session("u", "cli"), "find it"))
    assert ToolFinished("delegate", "The token is 42.") in events
    subagent_request, last_request = script.requests[1], script.requests[-1]
    assert subagent_request[1] == HumanMessage("Find the token", id=subagent_request[1].id)
    assert _tool_results(last_request) == ["The token is 42."]


async def test_the_subagents_tool_calls_stream_as_the_delegate_calls_progress(service, script):
    script.call("delegate", task="Say hi").call("bash", command="echo hi").reply("hi").reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "go"))
    tools = [e for e in events if isinstance(e, ToolStarted | ToolFinished)]
    assert tools == [
        ToolStarted("delegate", {"task": "Say hi"}),
        ToolStarted("bash", {"command": "echo hi"}, within="call-0"),
        ToolFinished("bash", "exit code: 0\nhi\n", within="call-0"),
        ToolFinished("delegate", "hi"),
    ]
    assert isinstance(tools[0], ToolStarted) and tools[0].id == "call-0"


async def test_subagents_get_only_the_tools_that_dont_talk_send_or_save(service, script):
    script.call("delegate", task="look around").reply("nothing").reply("ok")
    await collect(service.send(await service.session("u", "cli"), "go"))
    subagent_tools = {t.name for t in script.bound[1]}
    assert {"bash", "web_search", "search_memory", "read_email", "use_skill"} <= subagent_tools
    assert not subagent_tools & {"delegate", "send_message", "ask_user", "remember", "send_email", "schedule_job"}


async def test_an_approval_inside_resumes_the_subagent_where_it_stopped(service, script):
    script.call("delegate", task="clean up")
    script.call("bash", command="echo first").call("bash", command="rm -rf build").reply("Cleaned.")
    script.reply("Done.")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert approval.request["command"] == "rm -rf build"
    asked = len(script.requests)
    events = await collect(service.resume(session, {approval.interrupt_id: {"approved": False, "reason": "no"}}))
    # One more subagent call and the main agent's: nothing before the approval ran again.
    assert len(script.requests) == asked + 2
    assert any(r.startswith("The user rejected this (no).") for r in _tool_results(script.requests[-2]))
    assert ToolFinished("delegate", "Cleaned.") in events and isinstance(events[-1], Done)


async def test_parallel_subagents_pause_and_resume_separately(service, script):
    script.reply(
        tool_calls=[
            {"name": "delegate", "args": {"task": "a"}, "id": "d1"},
            {"name": "delegate", "args": {"task": "b"}, "id": "d2"},
        ]
    )
    script.call("bash", command="rm -rf a").call("bash", command="rm -rf a").reply("sub").reply("sub")
    script.reply("Both done.")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "both"))
    approvals = [e for e in events if isinstance(e, ApprovalRequired)]
    assert len(approvals) == 2
    decisions = {a.interrupt_id: {"approved": False, "reason": "no"} for a in approvals}
    events = await collect(service.resume(session, decisions))
    finished = [e for e in events if isinstance(e, ToolFinished)]
    assert [e for e in finished if not e.within] == [ToolFinished("delegate", "sub")] * 2
    assert {e.within for e in finished if e.within} == {"d1", "d2"}
    assert isinstance(events[-1], Done)


async def test_tool_calls_past_the_step_limit_dont_run(service, script, monkeypatch):
    monkeypatch.setattr(settings, "subagent_max_steps", 2)
    script.call("delegate", task="dig")
    script.call("bash", command="echo one").call("bash", command="echo two").reply("Found one.")
    script.reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "dig"))
    assert _tool_results(script.requests[3])[-1] == LIMIT_REACHED
    assert ToolFinished("delegate", "Found one.") in events


async def test_mcp_tools_that_can_change_things_dont_run_in_a_subagent(service, script):
    script.call("delegate", task="write")
    script.call("mcp__notes__write", text="x").reply("couldn't")
    script.reply("ok")
    await collect(service.send(await service.session("u", "cli"), "write"))
    assert "mcp__notes__write isn't available to a subagent" in _tool_results(script.requests[2])[0]


async def test_a_delegate_call_gives_its_subagent_alone_the_read_only_tools_of_the_plugins_it_names(
    service, script, monkeypatch
):
    route = {"type": "function", "function": {"name": "mcp__maps__route", "description": "A route", "parameters": {}}}
    monkeypatch.setattr(service._plugin_tools, "read_only_definitions", lambda: [route])
    monkeypatch.setattr(
        service._plugin_tools, "plugin_of", lambda name: "maps" if name.startswith("mcp__maps__") else None
    )
    script.call("delegate", task="How far is Rosario?", plugins=["maps"]).reply("300 km").reply("ok")
    script.call("delegate", task="Will it rain there?", plugins=["maps", "weather"]).reply("can't")
    session = await service.session("u", "cli")
    await collect(service.send(session, "how far is Rosario?"))
    await collect(service.send(session, "and the weather?"))
    names = [{t["function"]["name"] if isinstance(t, dict) else t.name for t in bound} for bound in script.bound]
    assert "mcp__maps__route" in names[1]
    assert not any("mcp__maps__route" in bound for bound in [names[0], *names[2:]])  # the conversation's stay
    assert _tool_results(script.requests[-1])[-1] == (
        "Not delegated: weather has no read-only tools a subagent can use. Plugins it can get: maps."
    )


async def test_scheduled_jobs_delegate_too(service, script):
    script.call("delegate", task="x").reply("found it").reply("ok")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    assert ToolFinished("delegate", "found it") in events


async def test_the_subagents_steps_show_again_inside_the_delegate_call_after_a_reload(service, script):
    script.call("delegate", task="Find the token")
    script.call("bash", command="echo token-in-a-long-log").reply("The token is 42.")
    script.reply("It's 42.")
    session = await service.session("u", "cli")
    await collect(service.send(session, "find it"))
    shown = await service.conversation_messages(session.thread_id)
    call = next(m for m in shown if m.role == "tool")
    assert (call.text, call.detail, call.output) == ("delegate", "Find the token", "The token is 42.")
    assert call.steps == [
        ShownStep("bash", {"command": "echo token-in-a-long-log"}, "exit code: 0\ntoken-in-a-long-log\n")
    ]
    # The main agent still reads only the answer.
    assert _tool_results(script.requests[-1]) == ["The token is 42."]


async def test_kept_steps_stop_at_a_length_and_other_tools_keep_none(service, script, monkeypatch):
    monkeypatch.setattr(subagent_steps, "_MAX_OUTPUT", 10)
    script.call("delegate", task="read").call("bash", command="seq 100").reply("done")
    script.call("bash", command="echo hi").reply("ok")
    session = await service.session("u", "cli")
    await collect(service.send(session, "go"))
    delegate, bash = [m for m in await service.conversation_messages(session.thread_id) if m.role == "tool"]
    assert delegate.steps[0].output == "exit code:\n…"
    assert (bash.text, bash.detail, bash.output, bash.steps) == ("bash", "echo hi", "exit code: 0\nhi\n", [])
    assert not bash.partial
