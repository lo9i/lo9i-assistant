from typing import Any
from urllib.parse import quote

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import (
    RunningTask,
    Sent,
    SessionNotFoundError,
    TasksBesideError,
    TaskSession,
    TaskSessionDetails,
    TaskStep,
    TaskTurn,
)

_ERRORS: dict[int, type[Exception]] = {404: SessionNotFoundError, 409: TasksBesideError}


class TasksApi:
    """Coding agents' tasks running in the background, and those a conversation started, shown beside it by session
    (core/agent_tasks/beside.py)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def running(self) -> list[RunningTask]:
        return [RunningTask(**t) for t in await self._transport.request("GET", "/agent-tasks/running")]

    async def sessions(self, thread_id: str) -> list[TaskSession]:
        found = await self._transport.request("GET", f"/conversations/{quote(thread_id)}/tasks")
        return [TaskSession(**s) for s in found]

    async def everywhere(self) -> list[TaskSession]:
        """Every conversation's sessions, the newest first."""
        return [TaskSession(**s) for s in await self._transport.request("GET", "/agent-tasks/sessions")]

    async def session(self, thread_id: str, session_id: str) -> TaskSessionDetails:
        """Its tasks with their steps. Raises SessionNotFoundError for an unknown session."""
        found = await self._transport.request("GET", _session(thread_id, session_id), errors=_ERRORS)
        return TaskSessionDetails(TaskSession(**found["session"]), [_turn(t) for t in found["turns"]], found["waiting"])

    async def message(self, thread_id: str, session_id: str, text: str) -> Sent:
        """Writes to the session's agent: between its steps while it works, else as its next task. Raises
        SessionNotFoundError for an unknown session, TasksBesideError when its next task can't start."""
        path = f"{_session(thread_id, session_id)}/messages"
        return (await self._transport.request("POST", path, json={"text": text}, errors=_ERRORS))["sent"]

    async def stop(self, thread_id: str, session_id: str) -> TaskSession:
        """Raises TasksBesideError when its agent isn't working."""
        path = f"{_session(thread_id, session_id)}/stop"
        return TaskSession(**await self._transport.request("POST", path, errors=_ERRORS))

    async def remove(self, thread_id: str, session_id: str) -> None:
        """Raises TasksBesideError while its agent works."""
        await self._transport.request("DELETE", _session(thread_id, session_id), errors=_ERRORS)


def _turn(found: dict[str, Any]) -> TaskTurn:
    steps = {key: [TaskStep(**s) for s in found[key]] for key in ("steps", "unread")}
    return TaskTurn(**{**found, **steps})


def _session(thread_id: str, session_id: str) -> str:
    return f"/conversations/{quote(thread_id)}/tasks/{quote(session_id)}"
