"""A handed-off agent's progress messages as a run's events."""

import json

from assistant.core.agent_tasks.steps import AgentSteps
from assistant.core.events import TextDelta, Thinking, ToolFinished, ToolStarted


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


def test_texts_apart_from_each_other_are_separate_paragraphs_and_thinking_is_its_own():
    steps = AgentSteps("Claude Code")
    events = _events(steps, {"kind": "text", "text": "One."}, {"kind": "thinking", "text": "Two?"})
    events += _events(steps, {"kind": "text", "text": "Three."}, {"kind": "text", "text": "Four."})
    assert events == [TextDelta("One."), Thinking("Two?"), TextDelta("Three."), TextDelta("\n\nFour.")]
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
