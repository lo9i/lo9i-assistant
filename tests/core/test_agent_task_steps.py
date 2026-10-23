"""A handed-off agent's progress messages as a run's events."""

import json

from assistant.core.agent_tasks.steps import AgentSteps, line
from assistant.core.events import TextDelta, ToolFinished, ToolStarted, UserSaid


def _events(steps: AgentSteps, *messages: dict | str) -> list:
    return [e for m in messages for e in steps.events(m if isinstance(m, str) else json.dumps(m))]


def test_a_subagents_tool_calls_go_inside_the_call_that_started_it_and_its_words_are_left_out():
    events = _events(
        AgentSteps("Claude Code"),
        {"kind": "tool", "tool": "Agent", "detail": "Find the bug", "id": "a1"},
        {"kind": "thinking", "text": "hm", "within": "a1"},
        {"kind": "tool", "tool": "Read", "detail": "/repo/app.py", "id": "r1", "within": "a1"},
        {"kind": "result", "tool": "Read", "text": "def main(): ...", "id": "r1", "within": "a1"},
        {"kind": "result", "tool": "Agent", "text": "Found it.", "id": "a1"},
    )
    assert events == [
        ToolStarted("Agent", {"detail": "Find the bug"}, id="a1"),
        ToolStarted("Read", {"detail": "/repo/app.py"}, id="r1", within="a1"),
        ToolFinished("Read", "def main(): ...", within="a1"),
        ToolFinished("Agent", "Found it."),
    ]


def test_texts_and_thinking_apart_from_each_other_are_separate_paragraphs_of_what_it_says():
    steps = AgentSteps("Claude Code")
    events = _events(steps, {"kind": "text", "text": "One."}, {"kind": "thinking", "text": "Two?"})
    events += _events(steps, {"kind": "text", "text": "Three."}, {"kind": "text", "text": "Four."})
    assert events == [TextDelta("One."), TextDelta("\n\nTwo?"), TextDelta("\n\nThree."), TextDelta("\n\nFour.")]
    assert steps.spoke


def test_notes_and_plain_lines_go_in_one_call_named_after_the_agent_closed_at_the_end():
    steps = AgentSteps("Copilot")
    events = _events(steps, {"kind": "note", "text": "Downloading the CLI"}, "Reading app.py", "42")
    call = events[0]
    assert call == ToolStarted("Copilot", {}, id=call.id) and call.id
    assert [e.name for e in events[1:]] == ["Downloading the CLI"] * 2 + ["Reading app.py"] * 2 + ["42"] * 2
    assert all(e.within == call.id for e in events[1:])
    assert steps.end("Done") == [ToolFinished("Copilot", "Done")] and not steps.spoke
    assert AgentSteps("Copilot").end("Done") == []


def test_words_stream_and_their_whole_block_isnt_shown_again():
    steps = AgentSteps("Claude Code")
    events = _events(
        steps,
        {"kind": "thinking_delta", "text": "The test "},
        {"kind": "thinking_delta", "text": "expects a list."},
        {"kind": "thinking", "text": "The test expects a list."},
        {"kind": "text_delta", "text": "Running "},
        {"kind": "text_delta", "text": "it."},
        {"kind": "text", "text": "Running it."},
        {"kind": "text_delta", "text": "Done."},
        {"kind": "text", "text": "Done."},
        {"kind": "text", "text": "Whole."},  # a block whose words didn't stream
        {"kind": "text_delta", "text": "sub", "within": "a1"},
    )
    assert events == [
        TextDelta("The test "),
        TextDelta("expects a list."),
        TextDelta("\n\nRunning "),
        TextDelta("it."),
        TextDelta("\n\nDone."),
        TextDelta("\n\nWhole."),
    ]
    assert [json.loads(line)["kind"] for line in steps.lines] == ["thinking", "text", "text", "text"]


def test_a_tasks_latest_steps_leave_out_the_streamed_words(tmp_path):
    from assistant.core.agent_tasks.records import TaskStore

    store = TaskStore(tmp_path)
    task = store.create("/repo", "fix it")
    lines = [
        {"kind": "text_delta", "text": "Run"},
        {"kind": "text", "text": "Running."},
        {"kind": "tool", "tool": "Bash"},
    ]
    (store.folder(task.id) / "progress.log").write_text("".join(json.dumps(line) + "\n" for line in lines))
    assert [json.loads(line)["kind"] for line in store.state(task.id).progress] == ["text", "tool"]
    assert store.state(task.id, progress_lines=0).progress == []


def test_a_message_the_user_sent_while_it_worked_shows_as_theirs_and_its_next_words_answer_it():
    steps = AgentSteps("Claude Code")
    events = _events(
        steps,
        {"kind": "text", "text": "Running the tests."},
        {"kind": "user", "text": "skip the slow ones", "id": "m1"},
        {"kind": "text_delta", "text": "Skipping"},
        {"kind": "text", "text": "Skipping"},
    )
    assert events == [TextDelta("Running the tests."), UserSaid("skip the slow ones"), TextDelta("Skipping")]
    assert steps.spoke and steps.reply("Skipping") == []
    assert line(json.dumps({"kind": "user", "text": "skip the slow ones"})) == "The user: skip the slow ones"
