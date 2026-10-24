"""History shows each tool call's arguments on one line and the start of its output; the whole call loads
when it's opened, and each step inside a delegate call or a handed-off agent's call when that's opened
(core/conversation/display.py)."""

import json

from langchain_core.messages import AIMessage, ToolMessage

from assistant.core import subagent_steps
from assistant.core.agent_tasks.steps import STEPS
from assistant.core.conversation.display import ShownCall, shown, tool_call, tool_call_step
from assistant.core.subagent_steps import SubagentAnswer, SubagentStep


def _call(args: dict, output: str | None, call_id: str = "c1") -> list:
    asked = AIMessage("", tool_calls=[{"name": "bash", "args": args, "id": call_id}])
    return [asked] if output is None else [asked, ToolMessage(output, tool_call_id=call_id, name="bash")]


def test_a_short_call_is_shown_whole():
    [call] = shown(_call({"command": "ls"}, "a.txt"))
    assert (call.role, call.text, call.detail, call.output) == ("tool", "bash", "ls", "a.txt")
    assert call.call_id == "c1" and not call.partial


def test_a_long_command_and_output_are_cut_and_partial():
    [call] = shown(_call({"command": "echo " + "a" * 200}, "x" * 500))
    assert len(call.detail) == 121 and call.detail.endswith("…")
    assert call.output == "x" * 200 + "…" and call.partial


def test_a_command_on_several_lines_is_shown_on_one():
    [call] = shown(_call({"command": "cd src\n  ls"}, ""))
    assert call.detail == "cd src ls" and call.partial


def test_several_arguments_read_as_one_line_and_load_in_full():
    [call] = shown(_call({"query": "rome hotels", "count": 3, "fresh": True}, "found"))
    assert call.detail == "query: rome hotels, count: 3, fresh: true" and call.partial


def test_a_call_without_arguments_or_a_result_has_nothing_more_to_load():
    [call] = shown(_call({}, None))
    assert (call.detail, call.output, call.partial) == ("", "", False)


def test_the_whole_call_is_found_by_its_id():
    messages = _call({"command": "seq 1 100"}, "1\n2\n" * 100, "c7")
    assert tool_call(messages, "c7") == ShownCall("bash", {"command": "seq 1 100"}, "1\n2\n" * 100)
    assert tool_call(_call({"command": "ls"}, None), "c1") == ShownCall("bash", {"command": "ls"}, "")
    assert tool_call(messages, "nope") is None


def _delegated(answer: str, steps: list[SubagentStep]) -> list:
    asked = AIMessage("", tool_calls=[{"name": "delegate", "args": {"task": "Find the token"}, "id": "d1"}])
    return [asked, subagent_steps.result(SubagentAnswer(answer, steps), "d1", "delegate")]


def test_a_delegate_calls_answer_and_steps_show_their_start_and_load_one_by_one():
    long_step = SubagentStep("bash", {"command": "cat log"}, "line\n" * 200)
    big_args = SubagentStep("write_file", {"path": "a.txt", "content": "x" * 500}, "ok")
    messages = _delegated("y" * 500, [long_step, big_args, SubagentStep("bash", {"command": "ls"}, "a.txt")])
    [call] = shown(messages)
    assert (call.call_id, call.detail, call.output, call.partial) == ("d1", "Find the token", "y" * 200 + "…", True)
    assert [(s.output[-1:], s.partial) for s in call.steps] == [("…", True), ("k", True), ("t", False)]
    assert call.steps[1].args == {"detail": "path: a.txt, content: " + "x" * 98 + "…"}
    assert tool_call(messages, "d1") == ShownCall("delegate", {"task": "Find the token"}, "y" * 500)
    assert tool_call_step(messages, "d1", 0) == ShownCall("bash", {"command": "cat log"}, "line\n" * 200)
    assert tool_call_step(messages, "d1", 1) == ShownCall("write_file", {"path": "a.txt", "content": "x" * 500}, "ok")
    assert tool_call_step(messages, "d1", 3) is None and tool_call_step(messages, "nope", 0) is None


def test_a_handed_off_agents_calls_show_their_start_and_load_by_the_reply_and_their_place():
    lines = [
        json.dumps({"kind": "tool", "tool": "Bash", "detail": "pytest", "id": "t0"}),
        json.dumps({"kind": "result", "tool": "Bash", "text": "F" * 500, "id": "t0"}),
        json.dumps({"kind": "tool", "tool": "Task", "detail": "find it", "id": "t1"}),
        json.dumps({"kind": "tool", "tool": "Grep", "detail": "def parse", "id": "s1", "within": "t1"}),
        json.dumps({"kind": "result", "tool": "Grep", "text": "g" * 500, "id": "s1", "within": "t1"}),
        json.dumps({"kind": "result", "tool": "Task", "text": "in parse.py", "id": "t1"}),
    ]
    messages = [AIMessage("Done.", id="r1", response_metadata={STEPS: lines})]
    bash, task, _ = shown(messages)
    assert (bash.call_id, bash.output, bash.partial) == ("agent~r1~0", "F" * 200 + "…", True)
    assert (task.call_id, task.partial, task.steps[0].partial) == ("agent~r1~1", False, True)
    assert tool_call(messages, "agent~r1~0") == ShownCall("Bash", {"detail": "pytest"}, "F" * 500)
    assert tool_call_step(messages, "agent~r1~1", 0) == ShownCall("Grep", {"detail": "def parse"}, "g" * 500)
    assert tool_call(messages, "agent~r2~0") is None
