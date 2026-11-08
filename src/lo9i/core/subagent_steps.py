"""What a subagent did for a delegate call (core/subagent.py), or the steps a task showed while task_status
waited for it (core/agent_tasks/tools.py), kept with the call's result so history shows them again after a
reload, inside the call, as they were shown live, with how the subagent did (its status line). It goes in the result's
`response_metadata`, which no model call sends, so the main agent still reads only the answer."""

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from langchain_core.messages import ToolMessage

# The keys in the delegate result's response_metadata.
STEPS = "subagent_steps"
STATUS = "subagent_status"
# The most of a step's output kept: enough to see what it found, without copying every page it read into
# the conversation's state, where it would stay for good.
_MAX_OUTPUT = 4000


@dataclass(frozen=True)
class SubagentStep:
    """One of the subagent's tool calls: the tool, what it was called with, and what it answered."""

    name: str
    args: dict[str, Any]
    output: str
    # When the subagent's model asked for it, as ISO 8601; "" when not known (a task's step, one kept before).
    at: str = field(default="", compare=False)


@dataclass(frozen=True)
class SubagentStatus:
    """How a subagent did, as the apps' status line under it shows: its model calls (`steps`, of `max_steps`, 0 for
    no limit), the tokens its last call took against its model's window (0 when not known), and when it started and
    ended (ISO 8601; "" while it works)."""

    steps: int
    max_steps: int
    context_tokens: int
    context_limit: int
    started_at: str
    ended_at: str = ""


@dataclass(frozen=True)
class SubagentAnswer:
    text: str
    steps: list[SubagentStep]
    status: SubagentStatus | None = None


def result(answer: SubagentAnswer, call_id: str, tool: str) -> ToolMessage:
    """The delegate call's result: the answer, with the steps and the subagent's status kept beside it."""
    kept: dict[str, Any] = {STEPS: [asdict(replace(s, output=_cut(s.output))) for s in answer.steps]}
    if answer.status is not None:
        kept[STATUS] = asdict(answer.status)
    return ToolMessage(answer.text, tool_call_id=call_id, name=tool, response_metadata=kept)


def of(message: ToolMessage) -> list[SubagentStep]:
    """The steps kept with a result; none for any other tool's."""
    kept = message.response_metadata.get(STEPS) or []
    return [SubagentStep(s.get("name", ""), s.get("args") or {}, s.get("output", ""), s.get("at", "")) for s in kept]


def status_of(message: ToolMessage) -> SubagentStatus | None:
    """The subagent's status kept with a delegate call's result; None for any other, or one kept before."""
    kept = message.response_metadata.get(STATUS)
    return SubagentStatus(**kept) if isinstance(kept, dict) else None


def _cut(output: str) -> str:
    return output if len(output) <= _MAX_OUTPUT else output[:_MAX_OUTPUT] + "\n…"
