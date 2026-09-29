"""AssistantService: the only core API that gateways use."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.core import observability
from assistant.core.attachments import Attachment, to_content
from assistant.core.config import settings
from assistant.core.context import Context
from assistant.core.events import Done, Error, Event
from assistant.core.graph import build_graph
from assistant.core.memory import Memory, open_memory
from assistant.core.stream_events import approval_events, to_events


@dataclass
class Session:
    user_id: str
    channel: str
    thread_id: str


class AssistantService:
    def __init__(self, memory: Memory, model: str):
        self._memory = memory
        self._graph = build_graph(memory, model)

    @classmethod
    @asynccontextmanager
    async def open(cls, model: str | None = None) -> AsyncIterator["AssistantService"]:
        observability.init_tracing()
        try:
            async with open_memory(settings.database_url) as memory:
                yield cls(memory, model or settings.model)
        finally:
            observability.flush()

    async def session(self, user_id: str, channel: str) -> Session:
        """The user's active conversation, shared by every channel."""
        item = await self._memory.store.aget(("threads", user_id), "active")
        thread_id = item.value["thread_id"] if item else await self.new_thread(user_id)
        return Session(user_id=user_id, channel=channel, thread_id=thread_id)

    async def new_thread(self, user_id: str) -> str:
        thread_id = f"{user_id}:{uuid4().hex[:12]}"
        await self._memory.store.aput(("threads", user_id), "active", {"thread_id": thread_id})
        return thread_id

    async def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]:
        try:
            content = to_content(text, attachments)
        except ValueError as e:
            yield Error(str(e))
            return
        async for event in self._run(session, {"messages": [HumanMessage(content=content)]}):
            yield event

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        """Answer pending approvals. `decisions` maps interrupt id to {"approved": bool, "reason": str}."""
        async for event in self._run(session, Command(resume=decisions)):
            yield event

    async def _run(self, session: Session, input: Any) -> AsyncIterator[Event]:
        async with self._thread_lock(session.thread_id):
            try:
                async for event in self._run_events(session, input):
                    yield event
            except Exception as e:
                yield Error(f"{type(e).__name__}: {e}")

    async def _run_events(self, session: Session, input: Any) -> AsyncIterator[Event]:
        config = _run_config(session)
        pending = await self._pending_approvals(config)
        # A new message can't be sent while tool calls wait for approval.
        if pending and not isinstance(input, Command):
            for event in pending:
                yield event
            return
        async for event in self._stream(session, input, config):
            yield event
            if isinstance(event, Error):
                return
        if not await self._pending_approvals(config):
            yield Done()

    async def _stream(self, session: Session, input: Any, config: RunnableConfig) -> AsyncIterator[Event]:
        context = Context(user_id=session.user_id, channel=session.channel)
        async for mode, data in self._graph.astream(input, config, context=context, stream_mode=["messages", "updates"]):
            for event in to_events(mode, data):
                yield event

    async def _pending_approvals(self, config: RunnableConfig) -> list[Event]:
        state = await self._graph.aget_state(config)
        return approval_events(state.interrupts)

    @asynccontextmanager
    async def _thread_lock(self, thread_id: str) -> AsyncIterator[None]:
        """One run per thread at a time, across all processes."""
        async with self._memory.pool.connection() as conn:
            await conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (thread_id,))
            try:
                yield
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (thread_id,))


def _run_config(session: Session) -> RunnableConfig:
    return {
        "configurable": {"thread_id": session.thread_id},
        "callbacks": observability.callbacks(),
        "metadata": {
            "langfuse_user_id": session.user_id,
            "langfuse_session_id": session.thread_id,
            "langfuse_tags": [session.channel],
        },
    }
