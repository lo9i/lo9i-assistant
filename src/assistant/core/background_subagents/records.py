"""What the Store keeps of each background subagent: its record (the task, the conversation it works for, its status,
what it's doing now and how it ended) and its steps, each a record of its own, so a long task doesn't write all its
steps again at each one. Kept by id across conversations, for a view of them all as well as each conversation's."""

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

from langgraph.store.base import BaseStore

from assistant.core.events import ApprovalRequired

_NAMESPACE = ("background_subagents",)
_STEPS = "background_subagent_steps"
# The most of a step's output kept: enough to see what it found (as core/subagent_steps.py keeps).
_MAX_OUTPUT = 4000
_LISTED = 10_000

Status = Literal["running", "waiting", "done", "failed", "stopped"]
RUNNING: Status = "running"
WAITING: Status = "waiting"
DONE: Status = "done"
FAILED: Status = "failed"
STOPPED: Status = "stopped"
ENDED: tuple[Status, ...] = (DONE, FAILED, STOPPED)


@dataclass
class BackgroundSubagent:
    id: str
    user_id: str
    # The conversation it works for, which its answer goes back to.
    thread_id: str
    # The channel that conversation was on when it was sent off: its approvals go there too.
    channel: str
    task: str
    # The named subagent a plugin brings (core/mcp/subagents.py); "" for the general one.
    agent: str
    # The plugins whose read-only tools it gets.
    plugins: list[str]
    started_at: str
    # running, waiting (for the user's answer), done, failed or stopped (by the user).
    status: Status = RUNNING
    ended_at: str = ""
    # What it's doing now: its tool calls in progress, one line; "" while it thinks.
    step: str = ""
    steps: int = 0
    # Its answer once done; what went wrong when it failed.
    result: str = ""
    # What it waits for the user's answer to.
    waiting: list[ApprovalRequired] = field(default_factory=list)

    @property
    def ended(self) -> bool:
        return self.status in ENDED


@dataclass
class BackgroundStep:
    """One of its tool calls: the tool, what it was called with, and once it finished, what it answered."""

    index: int
    call_id: str
    name: str
    args: dict[str, Any]
    output: str = ""
    done: bool = False


async def save(store: BaseStore, subagent: BackgroundSubagent) -> None:
    await store.aput(_NAMESPACE, subagent.id, asdict(subagent))


async def load(store: BaseStore, subagent_id: str) -> BackgroundSubagent | None:
    item = await store.aget(_NAMESPACE, subagent_id)
    return from_value(item.value) if item else None


async def listed(store: BaseStore, thread_id: str = "") -> list[BackgroundSubagent]:
    """Every one, or the conversation's, the newest first."""
    found = [from_value(item.value) for item in await store.asearch(_NAMESPACE, limit=_LISTED)]
    kept = [s for s in found if not thread_id or s.thread_id == thread_id]
    return sorted(kept, key=lambda s: s.started_at, reverse=True)


async def delete(store: BaseStore, subagent_id: str) -> None:
    for item in await store.asearch((_STEPS, subagent_id), limit=_LISTED):
        await store.adelete((_STEPS, subagent_id), item.key)
    await store.adelete(_NAMESPACE, subagent_id)


async def save_step(store: BaseStore, subagent_id: str, step: BackgroundStep) -> None:
    output = step.output if len(step.output) <= _MAX_OUTPUT else step.output[:_MAX_OUTPUT] + "\n…"
    await store.aput((_STEPS, subagent_id), f"{step.index:06d}", asdict(step) | {"output": output})


async def steps(store: BaseStore, subagent_id: str) -> list[BackgroundStep]:
    items = await store.asearch((_STEPS, subagent_id), limit=_LISTED)
    return sorted((BackgroundStep(**item.value) for item in items), key=lambda s: s.index)


def from_value(value: dict[str, Any]) -> BackgroundSubagent:
    """A record as the Store or the API gives it."""
    known = {f.name for f in fields(BackgroundSubagent)}
    kept = {k: v for k, v in value.items() if k in known}
    kept["waiting"] = [ApprovalRequired(**w) for w in kept.get("waiting", [])]
    return BackgroundSubagent(**kept)
