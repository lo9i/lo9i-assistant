"""Coding agents' tasks that are running, for the apps to show what each is doing: the conversation that
started it and its latest steps; the apps reload them on `agent_task_progress` events (core/agent_tasks/ends.py). The
tasks started from a conversation, shown beside it, and what the user writes their agents there
(core/agent_tasks/beside.py). And the messages queued in a conversation (core/conversation/queued.py)."""

import logging
from dataclasses import dataclass

from lo9i.core.agent.base import ServiceBase
from lo9i.core.agent_tasks.beside import (
    Sent,
    SessionNotFoundError,
    TasksBesideError,
    TaskSession,
    TaskSessionDetails,
    TaskStep,
    TaskTurn,
)
from lo9i.core.agent_tasks.service import AgentTaskError, FoundTask
from lo9i.core.agent_tasks.steps import line
from lo9i.core.background import short
from lo9i.core.config import settings
from lo9i.core.conversation import queued
from lo9i.core.conversation.queued import Queued

__all__ = [
    "RunningTask",
    "Sent",
    "SessionNotFoundError",
    "TaskSession",
    "TaskSessionDetails",
    "TaskStep",
    "TaskTurn",
    "TasksBesideError",
    "TasksMixin",
]

logger = logging.getLogger(__name__)

_ASKED = 120


@dataclass
class RunningTask:
    id: str
    # The coding agent's name (Claude Code).
    agent: str
    # The conversation that started it, or the one handed to the agent that it answers in.
    thread_id: str
    # The start of what it was asked.
    asked: str
    started_at: str
    # Its latest steps, one line each, oldest first.
    steps: list[str]


class TasksMixin(ServiceBase):
    async def running_tasks(self) -> list[RunningTask]:
        """The newest first."""
        found = [f for f in await self.agent_tasks.recent() if f.state.status == "running"]
        running = [await self._running(f) for f in found]
        return [task for task in running if task is not None]

    async def next_queued(self, user_id: str, thread_id: str) -> Queued | None:
        """The next message to send in the conversation now that its run ended (core/conversation/queued.py), which
        is no longer kept."""
        return await queued.take(self._storage.store, user_id, thread_id)

    async def queued_threads(self, user_id: str) -> list[str]:
        return await queued.threads(self._storage.store, user_id)

    async def queued_count(self, user_id: str) -> int:
        """How many messages wait to be sent, in every conversation: held back while a restart is pending."""
        return sum(len(messages) for messages in (await queued.waiting(self._storage.store, user_id)).values())

    async def _running(self, found: FoundTask) -> RunningTask | None:
        task = found.state.task
        try:
            state = (await self.agent_tasks.state(task.id)).state
            thread_id = await self._thread_of_task(task.id)
        except AgentTaskError:
            return None
        steps = [text for step in state.progress if (text := line(step))]
        return RunningTask(task.id, found.agent.name, thread_id, short(task.prompt, _ASKED), task.started_at, steps)

    async def _thread_of_task(self, task_id: str) -> str:
        """The conversation that started it, whose panel shows it, or the one handed to the agent that it answers in."""
        origin = await self._task_reports.origin(task_id)
        if origin is not None:
            return origin.thread_id
        return await self.tasks_beside.thread_of(settings.owner_id, task_id) or await self.agent_tasks.conversation(
            task_id
        )

    async def task_sessions(self, user_id: str, thread_id: str) -> list[TaskSession]:
        """The coding agents' sessions started from the conversation, shown beside it, oldest first."""
        return await self.tasks_beside.listed(user_id, thread_id)

    async def every_task_session(self, user_id: str) -> list[TaskSession]:
        """Every conversation's coding agents' sessions, the newest first."""
        return await self.tasks_beside.everywhere(user_id)

    async def task_session(self, user_id: str, thread_id: str, session_id: str) -> TaskSessionDetails:
        """Raises SessionNotFoundError for an unknown one."""
        return await self.tasks_beside.details(user_id, thread_id, session_id)

    async def message_task_session(self, user_id: str, thread_id: str, session_id: str, text: str) -> Sent:
        """What the user wrote the session's agent. Raises SessionNotFoundError for an unknown session,
        TasksBesideError when its next task can't start."""
        return await self.tasks_beside.send(user_id, thread_id, session_id, text)

    async def stop_task_session(self, user_id: str, thread_id: str, session_id: str) -> TaskSession:
        """Raises TasksBesideError when its agent isn't working."""
        return await self.tasks_beside.stop(user_id, thread_id, session_id)

    async def remove_task_session(self, user_id: str, thread_id: str, session_id: str) -> None:
        """Raises TasksBesideError while its agent works."""
        await self.tasks_beside.remove(user_id, thread_id, session_id)
