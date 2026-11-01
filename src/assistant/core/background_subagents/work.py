"""One background subagent at work: its graph run under a thread of its own (so its checkpoints are its own, and an
approval pauses only it), from where it stopped when the daemon started again. Each tool call it makes is a step,
kept and published as it starts and as it finishes; what it waits for the user's answer to is kept on its record
until it's answered."""

import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from langgraph.types import Command

from assistant.core import observability
from assistant.core.background import short
from assistant.core.background_subagents import records
from assistant.core.background_subagents.records import RUNNING, WAITING, BackgroundStep, BackgroundSubagent
from assistant.core.bus import EventBus
from assistant.core.context import CONVERSATION_ID, Context
from assistant.core.events import ApprovalRequired
from assistant.core.health import HealthLog
from assistant.core.skills.tracker import SkillScriptTracker
from assistant.core.stream_events import approval_events
from assistant.core.subagent import NO_BACKGROUND_ANSWER, SubagentGraph, SubagentRunner, answer
from assistant.core.usage.meter import CHANNEL, CONVERSATION

# How long a step's line is.
_LINE = 80

# Answers what the subagent waits for: each request's decision, by interrupt id.
Answers = Callable[[BackgroundSubagent, list[ApprovalRequired]], Awaitable[dict[str, Any]]]


def thread(subagent_id: str) -> str:
    """The thread its checkpoints are saved under."""
    return f"subagent:{subagent_id}"


class SubagentWork:
    def __init__(
        self, subagent: BackgroundSubagent, store: BaseStore, bus: EventBus, health: HealthLog, answers: Answers
    ) -> None:
        self.subagent = subagent
        self._store = store
        self._bus = bus
        self._health = health
        self._answers = answers
        # Its tool calls in progress, by call id.
        self._open: dict[str, BackgroundStep] = {}

    async def answer(self, runner: SubagentRunner, context: Context) -> str:
        """Its answer once it's done; raises what stopped it. Runs from where its checkpoints left it."""
        subagent = self.subagent
        graph = await runner.background_graph(subagent.agent)
        config = self.config()
        saved = await graph.aget_state(config)
        await self._reopen(list(saved.values.get("messages", [])) if saved.values else [])
        input: Any = (
            None if saved.values else await runner.background_start(subagent.task, subagent.plugins, subagent.agent)
        )
        while True:
            await self._stream(graph, input, config, context)
            state = await graph.aget_state(config)
            if not state.interrupts:
                return answer(state.values.get("messages", []), NO_BACKGROUND_ANSWER)
            input = Command(resume=await self._waiting(approval_events(state.interrupts)))

    def config(self) -> RunnableConfig:
        """Its thread, the conversation it works for (whose usage its model calls count in), and no step limit."""
        subagent = self.subagent
        return {
            "configurable": {"thread_id": thread(subagent.id), CONVERSATION_ID: subagent.thread_id},
            "recursion_limit": sys.maxsize,
            "callbacks": [*observability.callbacks(), SkillScriptTracker(self._health)],
            "metadata": {CONVERSATION: subagent.thread_id, CHANNEL: subagent.channel},
        }

    async def _reopen(self, messages: list[BaseMessage]) -> None:
        """The steps in progress when the daemon stopped. One its checkpoints don't call any more (the model's reply
        wasn't kept, so it's asked again) or did answer is closed, so no step stays in progress for good."""
        called = {c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
        answered = {m.tool_call_id: m.text for m in messages if isinstance(m, ToolMessage)}
        self._open = {}
        for step in await records.steps(self._store, self.subagent.id):
            if step.done:
                continue
            if step.call_id in called and step.call_id not in answered:
                self._open[step.call_id] = step
            else:
                step.output, step.done = answered.get(step.call_id, ""), True
                await records.save_step(self._store, self.subagent.id, step)
        self.subagent.step = "; ".join(line(s.name, s.args) for s in self._open.values())

    async def _stream(self, graph: SubagentGraph, input: Any, config: RunnableConfig, context: Context) -> None:
        async for update in graph.astream(input, config, context=context, stream_mode="updates"):
            for node, value in update.items():
                if node != "__interrupt__":
                    for message in _messages(value):
                        await self._took(message)

    async def _took(self, message: BaseMessage) -> None:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                step = BackgroundStep(self.subagent.steps, call["id"] or "", call["name"], call["args"])
                self.subagent.steps += 1
                self._open[step.call_id] = step
                await self._step(step)
        elif isinstance(message, ToolMessage) and (step := self._open.pop(message.tool_call_id, None)):
            step.output, step.done = message.text, True
            await self._step(step)

    async def _step(self, step: BackgroundStep) -> None:
        await records.save_step(self._store, self.subagent.id, step)
        self.subagent.step = "; ".join(line(s.name, s.args) for s in self._open.values())
        await self.save()
        self._bus.publish("subagent_step", id=self.subagent.id, thread_id=self.subagent.thread_id, step=asdict(step))

    async def _waiting(self, asked: list[ApprovalRequired]) -> dict[str, Any]:
        """Kept on its record while the user answers, which may take as long as they like. Each request leaves it
        as it's answered, so the apps show the next one."""
        subagent = self.subagent
        subagent.status, subagent.waiting = WAITING, list(asked)
        await self.save()

        async def one(request: ApprovalRequired) -> dict[str, Any]:
            decision = await self._answers(subagent, [request])
            subagent.waiting = [w for w in subagent.waiting if w.interrupt_id != request.interrupt_id]
            await self.save()
            return decision

        decisions: dict[str, Any] = {}
        for decided in await asyncio.gather(*(one(a) for a in asked)):
            decisions.update(decided)
        subagent.status, subagent.waiting = RUNNING, []
        await self.save()
        return decisions

    async def save(self) -> None:
        await records.save(self._store, self.subagent)
        publish(self._bus, self.subagent)


def publish(bus: EventBus, subagent: BackgroundSubagent) -> None:
    """A `subagents` event: the apps show its card again."""
    bus.publish("subagents", id=subagent.id, thread_id=subagent.thread_id, status=subagent.status)


def line(name: str, args: dict[str, Any]) -> str:
    """A tool call on one line: the tool, and its first argument when it's short text."""
    first = next((v for v in args.values() if isinstance(v, str | int | float)), None)
    return short(f"{name} {first}" if first is not None else name, _LINE)


def _messages(value: Any) -> list[BaseMessage]:
    """A node's update: the model's reply, or a tool call's result (the tool node, given one call, answers a list)."""
    if isinstance(value, dict):
        return list(value.get("messages", []))
    return [m for m in value if isinstance(m, BaseMessage)] if isinstance(value, list) else []
