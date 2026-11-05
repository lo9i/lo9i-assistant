"""The coding tasks started from each conversation, shown in a panel beside it (beside.py), kept in the Store per
conversation. Tasks are grouped by the agent's session they continue: the task the assistant started, then each one
following it up (the user writing to the agent from the panel, or the assistant's start_task with follow_up_of), so
a session is one tab of the panel, the agent's work and what it was told in order."""

from dataclasses import asdict, dataclass, field

from langgraph.store.base import BaseStore


@dataclass
class BesideSession:
    # The agent's session (Task.session), which every task in it continues.
    id: str
    # The plugin that brings the agent, and the agent's name.
    agent: str
    name: str
    title: str
    repository: str
    # Its tasks, oldest first.
    tasks: list[str]
    # The tasks the user started from the panel, writing to the agent; the assistant started the others.
    from_user: list[str] = field(default_factory=list)
    # What the user wrote to the agent while it couldn't take messages, sent as the next task once the last one ends.
    waiting: list[str] = field(default_factory=list)
    # Its last task runs, or what comes after its end wasn't settled yet (TasksBeside follows it).
    following: bool = True


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("tasks_beside", user_id)


async def of(store: BaseStore, user_id: str, thread_id: str) -> list[BesideSession]:
    """The conversation's, oldest first."""
    item = await store.aget(_namespace(user_id), thread_id)
    return [BesideSession(**kept) for kept in item.value["sessions"]] if item else []


async def every(store: BaseStore, user_id: str) -> dict[str, list[BesideSession]]:
    """Every conversation's, by conversation."""
    found = await store.asearch(_namespace(user_id), limit=1000)
    return {item.key: [BesideSession(**kept) for kept in item.value["sessions"]] for item in found}


async def save(store: BaseStore, user_id: str, thread_id: str, sessions: list[BesideSession]) -> None:
    if not sessions:
        await forget(store, user_id, thread_id)
        return
    await store.aput(_namespace(user_id), thread_id, {"sessions": [asdict(s) for s in sessions]})


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)


def find(sessions: list[BesideSession], session_id: str) -> BesideSession | None:
    return next((s for s in sessions if s.id == session_id), None)
