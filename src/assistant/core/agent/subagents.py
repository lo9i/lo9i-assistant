"""Subagents sent off in the background (core/background_subagents/), for the apps: a conversation's, or every one
(for a view of them all), each with its status and what it's doing; one's steps and answer; answering what one waits
for, stopping one, removing one that ended. A `subagents` event says one changed, a `subagent_step` event brings
each step as it starts and finishes."""

from dataclasses import dataclass
from typing import Any

from assistant.core.agent.base import ServiceBase
from assistant.core.background_subagents.records import BackgroundStep, BackgroundSubagent
from assistant.core.background_subagents.runner import SubagentError, SubagentNotFoundError

__all__ = [
    "BackgroundStep",
    "BackgroundSubagent",
    "SubagentDetails",
    "SubagentError",
    "SubagentNotFoundError",
    "SubagentsMixin",
]


@dataclass
class SubagentDetails:
    subagent: BackgroundSubagent
    # Its tool calls, oldest first.
    steps: list[BackgroundStep]


class SubagentsMixin(ServiceBase):
    async def background_subagents_of(self, thread_id: str = "") -> list[BackgroundSubagent]:
        """The conversation's, or every one, the newest first."""
        return await self.background_subagents.listed(thread_id)

    async def subagent_details(self, subagent_id: str) -> SubagentDetails:
        """Raises SubagentError for an unknown one."""
        return SubagentDetails(*await self.background_subagents.details(subagent_id))

    async def answer_subagent(self, subagent_id: str, interrupt_id: str, decision: dict[str, Any]) -> bool:
        """False when it doesn't wait for that any more. Raises SubagentError for an unknown one."""
        return await self.background_subagents.answer(subagent_id, interrupt_id, decision)

    async def stop_subagent(self, subagent_id: str) -> BackgroundSubagent:
        """Raises SubagentError for an unknown one, or one not working."""
        return await self.background_subagents.stop(subagent_id)

    async def remove_subagent(self, subagent_id: str) -> None:
        """Raises SubagentError for an unknown one, or one still working."""
        await self.background_subagents.remove(subagent_id)
