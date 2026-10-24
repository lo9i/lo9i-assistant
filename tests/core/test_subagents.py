"""Subagents (delegate): a task worked on with a fresh context, whose answer alone reaches the
conversation; approvals inside it pause the run and resume it where it stopped."""

from langchain_core.messages import HumanMessage, ToolMessage

from assistant.core import subagent_steps
from assistant.core.agent import Session
from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import ApprovalRequired, Done, ToolFinished, ToolStarted
from assistant.core.subagent import LIMIT_REACHED
from assistant.core.subagent_steps import SubagentStep
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
    assert "The user rejected this (no)." in _tool_results(script.requests[-2])
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


async def test_scheduled_jobs_dont_delegate(service, script):
    script.call("delegate", task="x").reply("ok")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.output.startswith("Not delegated: subagents don't run in scheduled jobs.")


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
        SubagentStep("bash", {"command": "echo token-in-a-long-log"}, "exit code: 0\ntoken-in-a-long-log\n")
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
    assert (bash.text, bash.detail, bash.output, bash.steps) == ("bash", "", "", [])
