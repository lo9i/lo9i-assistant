from collections.abc import AsyncIterator
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.core import observability
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.session import Session
from assistant.core.context import Context
from assistant.core.events import Done, Error, Event
from assistant.core.stream_events import approval_events, to_events


class RunsMixin(LockingMixin):
    """Executes one graph run and translates it into events."""

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
