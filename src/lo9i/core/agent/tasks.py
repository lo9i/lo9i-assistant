"""Coding agents' tasks that are running, for the apps to show what each is doing: the conversation that
started it and its latest steps. The apps reload them on `agent_task_progress` events (core/agent_tasks/ends.py).
And the messages queued in a conversation (core/conversation/queued.py), a coding task among them, which goes only
with the conversation handed to its agent."""

import logging
from dataclasses import dataclass

from lo9i.core import i18n, notifications
from lo9i.core.agent.base import ServiceBase
from lo9i.core.agent_tasks.service import AgentTaskError, FoundTask
from lo9i.core.agent_tasks.steps import line
from lo9i.core.background import short
from lo9i.core.conversation import handoffs, queued
from lo9i.core.conversation.queued import Queued

__all__ = ["RunningTask", "TasksMixin"]

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
        """The next message to send in the conversation now that its run ended (core/conversation/queued.py). A
        coding task kept for after a restart hands the conversation to its agent first, before it stops being kept,
        so the handoff never goes without it; one whose conversation was taken back from its agent before it went
        is dropped, and the user told, never sent to the assistant as if they had written it."""
        store = self._storage.store
        while (waiting := await queued.first(store, user_id, thread_id)) is not None:
            if waiting.hand_to is not None:
                await handoffs.hand(store, user_id, thread_id, waiting.hand_to)
            elif waiting.brief and not await self._handed_to(user_id, thread_id, waiting.brief):
                await queued.take(store, user_id, thread_id)
                await self._not_sent(user_id, thread_id, waiting)
                continue
            await queued.take(store, user_id, thread_id)
            return waiting
        return None

    async def _handed_to(self, user_id: str, thread_id: str, agent: str) -> bool:
        handoff = await handoffs.current(self._storage.store, user_id, thread_id)
        return handoff is not None and handoff.name == agent

    async def _not_sent(self, user_id: str, thread_id: str, task: Queued) -> None:
        logger.info("Dropped the task for %s queued in %s: the conversation was taken back.", task.brief, thread_id)
        t = await i18n.chosen(self._storage.store)
        text = t(
            "The task for {agent} wasn't sent: the conversation was taken back from it before it went. Ask for it "
            "again to start it.",
            agent=task.brief,
        )
        await notifications.add(self._storage.store, user_id, "background", t("Task not sent"), text, False, thread_id)

    async def queued_threads(self, user_id: str) -> list[str]:
        return await queued.threads(self._storage.store, user_id)

    async def queued_count(self, user_id: str) -> int:
        """How many messages wait to be sent, in every conversation: held back while a restart is pending."""
        return sum(len(messages) for messages in (await queued.waiting(self._storage.store, user_id)).values())

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
