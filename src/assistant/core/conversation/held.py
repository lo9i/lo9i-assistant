"""Runs held while an update installs (`hold_runs`, core/agent/runs.py): what the user sends then (a message with
its files, an answer to an approval), and a scheduled job's run due then, is kept here instead of refused, with the
channel it came from and where in it (`Origin`), and runs once lo9i is back on the update, or at once when the
update failed, in the order it came (daemon/held.py). Its files are saved as any message's, and the message keeps
their references. One Store record each, under a key that sorts by when it came, so the restart loses none. Until it
runs, its conversation's history lists what it adds there, marked as waiting (`messages`)."""

import time
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from langchain_core.messages import BaseMessage, HumanMessage, messages_from_dict, messages_to_dict
from langgraph.store.base import BaseStore
from langgraph.types import Command

# Who runs a held run again, and shows it (`Origin.kind`).
APPS = ""
CHAT = "chat"
JOB = "job"
# What the input of a handed-off agent's turn (core/agent/handoffs.py) is kept under.
_AGENT = "agent"
_RESUME = "resume"
_CLIENT = "client_id"


@dataclass(frozen=True)
class Origin:
    """Where a run came from beyond its channel, so it shows there when it runs again: the apps (`APPS`), which
    show it like any run announced, with the client that sent it in `data` (`from_app`); a channel's chat
    (`CHAT`), with the chat and the user's message there in `data`; a scheduled job's run (`JOB`), which the
    scheduler records."""

    kind: str = APPS
    data: dict[str, Any] = field(default_factory=dict)


def from_app(client_id: str) -> Origin:
    """A run an app's client sent, which is told where the inbox sent its message on when it runs later."""
    return Origin(APPS, {_CLIENT: client_id}) if client_id else Origin()


def client_of(origin: Origin) -> str:
    """The app's client that sent the run; "" for any other origin."""
    return str(origin.data.get(_CLIENT, "")) if origin.kind == APPS else ""


@dataclass(frozen=True)
class HeldRun:
    thread_id: str
    channel: str
    # The run's input, as `kept_input` or `kept_agent_turn` keep it.
    input: dict[str, Any]
    # What the run is announced with when it runs (daemon/runs.py, `RunHub.start`).
    text: str = ""
    brief: str = ""
    notice: str = ""
    origin: Origin = field(default_factory=Origin)
    # Its key once kept; "" before.
    id: str = ""


def kept_input(input: Any) -> dict[str, Any]:
    """A graph run's input as JSON: its messages, or the answers it resumes with."""
    if isinstance(input, Command):
        return {_RESUME: input.resume}
    return {key: messages_to_dict(value) if key == "messages" else value for key, value in input.items()}


def kept_agent_turn(message: HumanMessage, said: str) -> dict[str, Any]:
    """A handed-off agent's turn: the message the conversation keeps and what the agent is told."""
    return {_AGENT: {"message": messages_to_dict([message]), "said": said}}


def graph_input(kept: dict[str, Any]) -> Any:
    if _RESUME in kept:
        return Command(resume=kept[_RESUME])
    return {key: messages_from_dict(value) if key == "messages" else value for key, value in kept.items()}


def agent_turn(kept: dict[str, Any]) -> tuple[HumanMessage, str] | None:
    """The message and what the agent is told, for a handed-off agent's turn; None for a graph run."""
    if _AGENT not in kept:
        return None
    turn = kept[_AGENT]
    message = messages_from_dict(turn["message"])[0]
    if not isinstance(message, HumanMessage):
        raise ValueError(f"A held agent turn keeps the user's message, not a {message.type} message.")
    return message, str(turn["said"])


def messages(kept: dict[str, Any]) -> list[BaseMessage]:
    """The messages the run adds to its conversation as it starts: none for the answers it resumes with."""
    if (turn := agent_turn(kept)) is not None:
        return [turn[0]]
    if _RESUME in kept:
        return []
    return list(graph_input(kept).get("messages", []))


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("held_runs", user_id)


async def keep(store: BaseStore, user_id: str, run: HeldRun) -> str:
    """Returns its id."""
    held_id = f"{time.time_ns():020d}-{uuid4().hex[:8]}"
    value = asdict(run)
    value.pop("id")
    await store.aput(_namespace(user_id), held_id, value)
    return held_id


async def take(store: BaseStore, user_id: str, held_id: str) -> bool:
    """No longer kept, as it runs. False when it wasn't any more: it ran already."""
    if await store.aget(_namespace(user_id), held_id) is None:
        return False
    await store.adelete(_namespace(user_id), held_id)
    return True


async def load(store: BaseStore, user_id: str, held_id: str) -> HeldRun | None:
    item = await store.aget(_namespace(user_id), held_id)
    return _held(item.key, item.value) if item else None


async def waiting(store: BaseStore, user_id: str) -> list[HeldRun]:
    """Oldest first."""
    items = await store.asearch(_namespace(user_id), limit=10_000)
    return [_held(item.key, item.value) for item in sorted(items, key=lambda i: i.key)]


def _held(key: str, value: dict[str, Any]) -> HeldRun:
    return HeldRun(**{**value, "origin": Origin(**value["origin"]), "id": key})
