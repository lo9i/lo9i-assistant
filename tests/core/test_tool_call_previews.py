"""History shows each tool call's arguments on one line and the start of its output; the whole call loads
when it's opened (core/conversation/display.py)."""

from langchain_core.messages import AIMessage, ToolMessage

from assistant.core.conversation.display import ShownCall, shown, tool_call


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
