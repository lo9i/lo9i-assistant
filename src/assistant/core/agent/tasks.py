"""Coding agents' tasks that are running, for the apps to show what each is doing: the conversation that
started it and its latest steps. The apps reload them on `agent_task_progress` events (core/agent_tasks/ends.py)."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.agent_tasks.service import AgentTaskError, FoundTask
from assistant.core.agent_tasks.steps import line
from assistant.core.background import short
from assistant.core.conversation import queued
from assistant.core.conversation.queued import Queued

__all__ = ["RunningTask", "TasksMixin"]

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
        """The next message to send in the conversation now that its run ended (core/conversation/queued.py)."""
        return await queued.take(self._storage.store, user_id, thread_id)

    async def queued_threads(self, user_id: str) -> list[str]:
        return await queued.threads(self._storage.store, user_id)

    async def _running(self, found: FoundTask) -> RunningTask | None:
        task = found.state.task
        try:
            state = (await self.agent_tasks.state(task.id)).state
            origin = await self._task_reports.origin(task.id)
            thread_id = origin.thread_id if origin else await self.agent_tasks.conversation(task.id)
        except AgentTaskError:
            return None
        steps = [text for step in state.progress if (text := line(step))]
        return RunningTask(task.id, found.agent.name, thread_id, short(task.prompt, _ASKED), task.started_at, steps)
