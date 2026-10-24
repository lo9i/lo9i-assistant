"""What a subagent did for a delegate call (core/subagent.py), kept with the call's result so history shows
it again after a reload, inside the call, as it was shown live. It goes in the result's
`response_metadata`, which no model call sends, so the main agent still reads only the answer."""

from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.messages import ToolMessage

# The key in the delegate result's response_metadata.
STEPS = "subagent_steps"
# The most of a step's output kept: enough to see what it found, without copying every page it read into
# the conversation's state, where it would stay for good.
_MAX_OUTPUT = 4000


@dataclass(frozen=True)
class SubagentStep:
    """One of the subagent's tool calls: the tool, what it was called with, and what it answered."""

    name: str
    args: dict[str, Any]
    output: str


@dataclass(frozen=True)
class SubagentAnswer:
    text: str
    steps: list[SubagentStep]


def result(answer: SubagentAnswer, call_id: str, tool: str) -> ToolMessage:
    """The delegate call's result: the answer, with the steps kept beside it."""
    kept = [asdict(SubagentStep(s.name, s.args, _cut(s.output))) for s in answer.steps]
    return ToolMessage(answer.text, tool_call_id=call_id, name=tool, response_metadata={STEPS: kept})


def of(message: ToolMessage) -> list[SubagentStep]:
    """The steps kept with a result; none for any other tool's."""
    kept = message.response_metadata.get(STEPS) or []
    return [SubagentStep(s.get("name", ""), s.get("args") or {}, s.get("output", "")) for s in kept]


def _cut(output: str) -> str:
    return output if len(output) <= _MAX_OUTPUT else output[:_MAX_OUTPUT] + "\n…"
