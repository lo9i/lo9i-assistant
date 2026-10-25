"""The day's problems in the conversations, read from their checkpoints: runs that failed and tool calls left
without results. A turn (a user message and what came after it) written that day counts once, as the worst it
shows: its run failed with an error the checkpoint keeps (only the last run's is kept), tool calls never got a
result (a run cancelled while tools ran answers them, so these ended with an error), or no reply came (the run
failed, or was stopped before the assistant answered). The turn a run is still on, or that waits for an answer,
isn't counted."""

import re
from collections.abc import Collection, Sequence
from datetime import date, datetime
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from langgraph.types import StateSnapshot

from assistant.core import conversations
from assistant.core.conversation.turn_header import said, sent_at
from assistant.core.conversation.unanswered import unanswered
from assistant.core.doctor.causes import Occurrence
from assistant.core.doctor.clock import day_of, header_time
from assistant.core.doctor.model import ThreadRef

NO_REPLY = "A message got no reply: its run failed or was stopped"
# An exception's repr: `OperationalError('database is locked')`.
_REPR = re.compile(r"^(\w+)\((['\"])(.*)\2\)$", re.DOTALL)


class ConversationStates(Protocol):
    """The graph, which reads a conversation's latest checkpoint."""

    async def aget_state(self, config: RunnableConfig, *, subgraphs: bool = False) -> StateSnapshot: ...


async def day_occurrences(
    store: BaseStore, states: ConversationStates, user_id: str, day: date, running: Collection[str]
) -> list[Occurrence]:
    """`running`: the conversations a run is on now."""
    found: list[Occurrence] = []
    for conversation in await conversations.recent(store, user_id):
        if day_of(datetime.fromisoformat(conversation.updated_at)) < day:
            continue
        snapshot = await states.aget_state({"configurable": {"thread_id": conversation.thread_id}})
        busy = conversation.thread_id in running or bool(snapshot.interrupts)
        found += _occurrences(
            snapshot, ThreadRef(thread_id=conversation.thread_id, title=conversation.title), day, busy
        )
    return found


def _occurrences(snapshot: StateSnapshot, thread: ThreadRef, day: date, busy: bool) -> list[Occurrence]:
    turns = _turns(snapshot.values.get("messages", []))
    if busy:
        turns = turns[:-1]
    found: list[Occurrence] = []
    for i, turn in enumerate(turns):
        at = _written(turn[0])
        if at is not None and day_of(at) == day:
            last = i == len(turns) - 1 and not busy
            found += _turn(turn, at, thread, _failure(snapshot) if last else None)
    return found


def _turn(
    turn: Sequence[BaseMessage], at: datetime, thread: ThreadRef, failure: tuple[str, str] | None
) -> list[Occurrence]:
    """`failure`: the step the turn's run failed at and its error, when the checkpoint keeps it."""
    if failure is not None:
        step, error = failure
        return [Occurrence(f"A run failed: {error}", step, at, example=error, thread=thread)]
    if calls := unanswered(turn):
        return [
            Occurrence(f"{c['name']} never got a result: its run ended with an error", c["name"], at, thread=thread)
            for c in calls
        ]
    if not any(isinstance(m, AIMessage) for m in turn[1:]):
        return [Occurrence(NO_REPLY, "", at, example=_said(turn[0]), thread=thread)]
    return []


def _failure(snapshot: StateSnapshot) -> tuple[str, str] | None:
    """The step the conversation's last run failed at and its error, which its checkpoint keeps."""
    failed = next((t for t in snapshot.tasks if t.error is not None), None)
    if failed is None:
        return None
    return failed.name, _error_text(failed.error)


def _error_text(error: object) -> str:
    """Like "OperationalError: database is locked". A checkpoint keeps the error as its repr."""
    if isinstance(error, BaseException):
        return f"{type(error).__name__}: {error}"
    match = _REPR.match(str(error))
    return f"{match[1]}: {match[3]}" if match else str(error)


def _turns(messages: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
    turns: list[list[BaseMessage]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            turns.append([message])
        elif turns:
            turns[-1].append(message)
    return turns


def _written(message: BaseMessage) -> datetime | None:
    """When the user wrote it, from its turn header; None without one."""
    written = sent_at(message) if isinstance(message, HumanMessage) else None
    return header_time(written) if written else None


def _said(message: BaseMessage) -> str:
    text = said(message)
    return text if len(text) <= 500 else text[:499] + "…"
