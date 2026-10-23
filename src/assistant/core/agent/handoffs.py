"""Conversations handed to a plugin's agent, like Claude Code (core/conversation/handoffs.py): switching
from the apps, and a message's run when the agent answers it instead of the assistant's model."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from assistant.core import inbox
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.agent_tasks.service import AgentTaskError
from assistant.core.agent_tasks.steps import STEPS, AgentSteps, streamed
from assistant.core.background import short
from assistant.core.bus import EventBus
from assistant.core.conversation import agent_folders, handoffs, queued
from assistant.core.conversation.agent_folders import AgentFolders, FolderError, FolderListing
from assistant.core.conversation.handoffs import Agent, Handoff
from assistant.core.events import Done, Error, Event

__all__ = ["Agent", "AgentFolders", "FolderError", "FolderListing", "Handoff", "HandoffError", "HandoffsMixin"]

# How much of the agent's reply, or of what went wrong, the apps' notice shows.
_FINISHED = 200


class HandoffError(Exception):
    pass


class HandoffsMixin(RunsMixin):
    async def agents(self) -> list[Agent]:
        """The agents installed plugins bring, for the apps' commands."""
        return await handoffs.agents(self._storage.store)

    async def conversation_agent(self, user_id: str, thread_id: str) -> Handoff | None:
        return await handoffs.current(self._storage.store, user_id, thread_id)

    async def hand_conversation(self, user_id: str, thread_id: str, command: str, folder: str) -> Handoff:
        """From the next message, the agent answers in `folder`. Raises HandoffError for the inbox, which
        routes every message, an unknown agent or a folder that doesn't exist."""
        if thread_id == await inbox.current(self._storage.store, user_id):
            raise HandoffError("The inbox sends each message on, so it can't be handed over: start a conversation.")
        agent = next((a for a in await self.agents() if a.command == command), None)
        if agent is None:
            raise HandoffError(await self._no_agent(command))
        where = Path(folder).expanduser()
        if where == agent_folders.workspace():
            await agent_folders.ensure_workspace()
        if not where.is_absolute() or not where.is_dir():
            raise HandoffError(f"{folder} isn't an existing folder. Give its full path.")
        handoff = Handoff(agent.server, agent.command, agent.name, str(where))
        await handoffs.hand(self._storage.store, user_id, thread_id, handoff)
        await agent_folders.remember(self._storage.store, user_id, where)
        return handoff

    async def _no_agent(self, command: str) -> str:
        if name := await handoffs.outdated(self._storage.store, command):
            return f"{name} was written for an older version of lo9i. Update it in Plugins to use /{command}."
        return f"No plugin brings /{command}. Install it from Plugins."

    async def agent_folders(self, user_id: str) -> AgentFolders:
        """The folders the apps offer to hand a conversation to: the workspace and the ones used before."""
        return await agent_folders.offered(self._storage.store, user_id)

    async def child_folders(self, folder: str) -> FolderListing:
        """The folders inside `folder`, to browse to one. Raises FolderError."""
        return await agent_folders.children(folder)

    async def take_back_conversation(self, user_id: str, thread_id: str) -> None:
        await handoffs.take_back(self._storage.store, user_id, thread_id)

    async def message_agent(self, user_id: str, thread_id: str, text: str) -> None:
        """Passes `text` on to the agent's task working in the conversation, which takes it between its
        steps; it shows among them. Raises HandoffError when none is working, or its agent can't take
        messages while it works."""
        await self._tell_agent(user_id, thread_id, lambda task: self.agent_tasks.message(task, text))

    async def interrupt_agent(self, user_id: str, thread_id: str) -> None:
        """Stops the step the agent's task in the conversation is taking; the task waits for the user's
        next message (message_agent). Raises HandoffError as message_agent does."""
        await self._tell_agent(user_id, thread_id, self.agent_tasks.interrupt)

    async def _tell_agent(self, user_id: str, thread_id: str, tell: Callable[[str], Awaitable[None]]) -> None:
        handoff = await handoffs.current(self._storage.store, user_id, thread_id)
        if handoff is None:
            raise HandoffError("This conversation isn't handed to an agent.")
        try:
            task = await self.agent_tasks.working_in(handoff.server, thread_id, handoff.folder)
            if not task:
                raise HandoffError(f"{handoff.name} isn't working on anything now. Send it as a new message.")
            await tell(task)
        except AgentTaskError as e:
            raise HandoffError(str(e)) from e

    async def _handed_off(
        self, session: Session, handoff: Handoff, message: HumanMessage, said: str
    ) -> AsyncIterator[Event]:
        async for event in self._run_with(session, lambda: self._agent_turn(session, handoff, message, said)):
            yield event

    async def _agent_turn(
        self, session: Session, handoff: Handoff, message: HumanMessage, said: str
    ) -> AsyncIterator[Event]:
        """The agent answers, its thinking, text and tool calls shown as it works; the message and its
        reply are added to the conversation."""
        steps = AgentSteps(handoff.name)
        reported: asyncio.Queue[str] = asyncio.Queue()
        asking = asyncio.create_task(self._ask_agent(session, handoff, said, reported))
        async for step in _steps_while(asking, reported):
            for event in steps.events(step):
                yield event
        try:
            reply = await asking
        except HandoffError as e:
            for event in [*steps.end("Failed"), Error(str(e))]:
                yield event
            await self._agent_finished(session, handoff, False, str(e))
            return
        for event in steps.end("Done"):
            yield event
        config: RunnableConfig = {"configurable": {"thread_id": session.thread_id}}
        # Written as the agent node's output: the graph reads it as a finished turn, nothing left to run.
        # Its steps go with the reply, for history; no model call sends response_metadata.
        answer = AIMessage(reply, response_metadata={STEPS: steps.lines})
        await self._graph.aupdate_state(config, {"messages": [message, answer]}, as_node="agent")
        await self._agent_finished(session, handoff, True, reply)
        for event in [*steps.reply(reply), Done()]:
            yield event

    async def _agent_finished(self, session: Session, handoff: Handoff, ok: bool, text: str) -> None:
        """The agent is done with what the user gave it, and waits for them: an `agent_finished` event, which
        the apps tell the user of. Not while another message waits to go to it (core/conversation/queued.py):
        the job goes on with that one. A run the user stopped isn't one they need telling of."""
        if session.thread_id in await queued.threads(self._storage.store, session.user_id):
            return
        self.bus.publish(
            "agent_finished", thread_id=session.thread_id, agent=handoff.name, ok=ok, text=short(text, _FINISHED)
        )

    async def _ask_agent(self, session: Session, handoff: Handoff, said: str, steps: asyncio.Queue[str]) -> str:
        """Raises HandoffError with what went wrong, for the user."""
        agent = next((a for a in await self.agents() if a.server == handoff.server), None)
        if agent is None:
            raise HandoffError(f"{handoff.name} isn't installed or is turned off. /{handoff.command} off goes back.")
        reported = _Steps(steps, self.bus, session.thread_id)
        try:
            return await self.agent_tasks.converse(agent.server, session.thread_id, handoff.folder, said, reported)
        except AgentTaskError as e:
            raise HandoffError(f"{handoff.name}: {e}") from e
        finally:
            # Its end too, so the apps' list of running tasks drops it.
            reported.progressed()


class _Steps:
    """Each line the agent's worker writes is a step it took (core/agent_tasks/steps.py). Each step, not
    the words of one as they stream, is an `agent_task_progress` event, as for a task start_task started
    (core/agent_tasks/ends.py), so the apps' list of running tasks follows it."""

    def __init__(self, steps: asyncio.Queue[str], bus: EventBus, thread_id: str) -> None:
        self._steps = steps
        self._bus = bus
        self._thread_id = thread_id

    async def __call__(self, step: str) -> None:
        self._steps.put_nowait(step)
        if not streamed(step):
            self.progressed()

    def progressed(self) -> None:
        self._bus.publish("agent_task_progress", thread_id=self._thread_id)


async def _steps_while(asking: asyncio.Task[str], steps: asyncio.Queue[str]) -> AsyncIterator[str]:
    """The steps as they come, until the agent has replied. Stopping the run stops the task too."""
    try:
        while not (asking.done() and steps.empty()):
            step = asyncio.ensure_future(steps.get())
            await asyncio.wait({asking, step}, return_when=asyncio.FIRST_COMPLETED)
            if step.done():
                yield step.result()
            else:
                step.cancel()
    finally:
        asking.cancel()
