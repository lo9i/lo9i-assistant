import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from assistant.core import checkpoints, observability
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.search import SearchMixin
from assistant.core.agent.session import Session
from assistant.core.context import Context
from assistant.core.events import ApprovalRequired, Cancelled, Done, Error, Event
from assistant.core.health import HealthLog
from assistant.core.skills.tracker import SkillScriptTracker
from assistant.core.stream_events import approval_events, to_events
from assistant.core.usage.log import UsageLog
from assistant.core.usage.meter import CHANNEL, CONVERSATION
from assistant.core.usage.tracker import UsageTracker

# The result of a tool call that a cancelled run never finished. Every tool call needs a result
# before the model is called again.
_CANCELLED_TOOL = "[cancelled by the user before it finished]"


class RunsMixin(LockingMixin, SearchMixin):
    """Executes one graph run and translates it into events. A run can be cancelled."""

    async def cancel(self, thread_id: str) -> bool:
        """Stop the conversation's run in progress; its events end with Cancelled. Returns
        whether a run was in progress."""
        task = self._active_runs.get(thread_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def runs_in_progress(self) -> int:
        return len(self._active_runs)

    async def until_no_runs(self) -> None:
        """Returns once no conversation has a run in progress."""
        await self._no_runs.wait()

    async def _run(self, session: Session, input: Any) -> AsyncIterator[Event]:
        async for event in self._run_with(session, lambda: self._run_events(session, input)):
            yield event

    async def _run_with(self, session: Session, events: Callable[[], AsyncIterator[Event]]) -> AsyncIterator[Event]:
        """A run of the conversation: the graph's, or a handed-off agent's (handoffs.py). One at a time
        per conversation, cancellable, and indexed and pruned when it ends."""
        async with self._thread_lock(session.thread_id):
            async for event in self._cancellable(session, events):
                yield event
            await self._index_after_run(session.user_id, session.thread_id)
            await checkpoints.prune(self._storage.checkpointer, session.thread_id)

    async def prune_checkpoints(self) -> int:
        """Prunes the conversations saved before runs pruned their own (core/checkpoints.py), one at a
        time under its lock. Returns how many checkpoints went."""
        pruned = 0
        for thread_id in await checkpoints.prunable(self._storage.checkpointer):
            async with self._thread_lock(thread_id):
                pruned += await checkpoints.prune(self._storage.checkpointer, thread_id)
        return pruned

    async def _cancellable(self, session: Session, produce: Callable[[], AsyncIterator[Event]]) -> AsyncIterator[Event]:
        """Runs in a task of its own, so `cancel` stops the run and never the caller reading the events
        (the run hub, a Telegram handler)."""
        events: asyncio.Queue[Event | None] = asyncio.Queue()
        task = asyncio.create_task(self._produce(produce, events))
        # A callback, not a `finally` in the task: a task cancelled before it starts never runs one.
        task.add_done_callback(lambda _: events.put_nowait(None))
        self._active_runs[session.thread_id] = task
        self._no_runs.clear()
        try:
            while (event := await events.get()) is not None:
                yield event
        finally:
            self._active_runs.pop(session.thread_id, None)
            if not self._active_runs:
                self._no_runs.set()
            task.cancel()  # Stops the graph when the caller stops reading; no-op once it's done.
        if task.cancelled():
            await self._answer_open_tool_calls(session.thread_id)
            yield Cancelled()

    async def _produce(self, produce: Callable[[], AsyncIterator[Event]], events: asyncio.Queue[Event | None]) -> None:
        try:
            async for event in produce():
                events.put_nowait(event)
        except Exception as e:
            events.put_nowait(Error(f"{type(e).__name__}: {e}"))

    async def pending_approvals(self, thread_id: str) -> list[ApprovalRequired]:
        """The approvals the conversation's run stopped for, still waiting for an answer."""
        return await self._pending_approvals({"configurable": {"thread_id": thread_id}})

    async def _answer_open_tool_calls(self, thread_id: str) -> None:
        """A run cancelled while tools ran leaves calls without results. They get one saying so,
        appended like any tool result, so the next model call is valid."""
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self._graph.aget_state(config)
        results = [
            ToolMessage(_CANCELLED_TOOL, tool_call_id=c["id"], name=c["name"]) for c in _open_calls(state.values)
        ]
        if results:
            await self._graph.aupdate_state(config, {"messages": results}, as_node="tools")

    async def _run_events(self, session: Session, input: Any) -> AsyncIterator[Event]:
        config = _run_config(session, self._storage.usage, self._health)
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
        context = Context(
            user_id=session.user_id,
            channel=session.channel,
            bus=self.bus,
            outbox=self.outbox,
            secrets=self.secrets,
            forwards_approvals=self.approvals.available,
            search=self._storage.search,
            recall=self._recall,
            subagents=self._subagents,
            mcp=self.mcp,
        )
        async for namespace, mode, data in self._graph.astream(
            input, config, context=context, stream_mode=["messages", "updates", "custom"], subgraphs=True
        ):
            # astream types its items as `dict | Any`; with subgraphs=True they're (namespace, mode, data).
            for event in to_events(cast(tuple[str, ...], namespace), mode, data):
                yield event

    async def _pending_approvals(self, config: RunnableConfig) -> list[ApprovalRequired]:
        state = await self._graph.aget_state(config)
        return approval_events(state.interrupts)


def _open_calls(values: dict[str, Any]) -> list[dict[str, Any]]:
    """Tool calls of the last assistant message that have no result yet."""
    messages: list[BaseMessage] = values.get("messages", [])
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    last = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    return [dict(c) for c in last.tool_calls if c["id"] not in answered] if last else []


def _run_config(session: Session, usage: UsageLog, health: HealthLog) -> RunnableConfig:
    tracker = UsageTracker(usage, session.thread_id, session.channel)
    return {
        "configurable": {"thread_id": session.thread_id},
        "callbacks": [*observability.callbacks(), tracker, SkillScriptTracker(health)],
        "metadata": {
            CONVERSATION: session.thread_id,
            CHANNEL: session.channel,
            "langfuse_user_id": session.user_id,
            "langfuse_session_id": session.thread_id,
            "langfuse_tags": [session.channel],
        },
    }
