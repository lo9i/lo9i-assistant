import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.attachments import Attachment, to_content
from assistant.core.events import Error, Event


class MessagingMixin(RunsMixin):
    """Public entry points for sending a message and answering approvals."""

    async def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]:
        try:
            content = await asyncio.to_thread(to_content, text, attachments)
        except ValueError as e:
            yield Error(str(e))
            return
        async for event in self._run(session, {"messages": [HumanMessage(content=content)]}):
            yield event

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        """Answer pending approvals. `decisions` maps interrupt id to {"approved": bool, "reason": str}."""
        async for event in self._run(session, Command(resume=decisions)):
            yield event
