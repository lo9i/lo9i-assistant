"""Conversations handed to a plugin's agent, like Claude Code (core/conversation/handoffs.py): switching
from the apps, and a message's run when the agent answers it instead of the assistant's model."""

from collections.abc import AsyncIterator
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from mcp.shared.exceptions import MCPError

from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.conversation import agent_folders, handoffs
from assistant.core.conversation.agent_folders import AgentFolders, FolderError, FolderListing
from assistant.core.conversation.handoffs import Agent, Handoff
from assistant.core.events import Done, Error, Event, TextDelta, ToolFinished, ToolStarted
from assistant.core.mcp.connection import ConnectionLostError, NotConnectedError
from assistant.core.mcp.tools import render

__all__ = ["Agent", "AgentFolders", "FolderError", "FolderListing", "Handoff", "HandoffError", "HandoffsMixin"]


class HandoffError(Exception):
    pass


class HandoffsMixin(RunsMixin):
    async def agents(self) -> list[Agent]:
        """The agents installed plugins bring, for the apps' commands."""
        return await handoffs.agents(self._storage.store)

    async def conversation_agent(self, user_id: str, thread_id: str) -> Handoff | None:
        return await handoffs.current(self._storage.store, user_id, thread_id)

    async def hand_conversation(self, user_id: str, thread_id: str, command: str, folder: str) -> Handoff:
        """From the next message, the agent answers in `folder`. Raises HandoffError for an unknown agent or
        a folder that doesn't exist."""
        agent = next((a for a in await self.agents() if a.command == command), None)
        if agent is None:
            raise HandoffError(f"No plugin brings /{command}. Install it from Plugins.")
        where = Path(folder).expanduser()
        if where == agent_folders.workspace():
            await agent_folders.ensure_workspace()
        if not where.is_absolute() or not where.is_dir():
            raise HandoffError(f"{folder} isn't an existing folder. Give its full path.")
        handoff = Handoff(agent.server, agent.command, agent.name, str(where))
        await handoffs.hand(self._storage.store, user_id, thread_id, handoff)
        await agent_folders.remember(self._storage.store, user_id, where)
        return handoff

    async def agent_folders(self, user_id: str) -> AgentFolders:
        """The folders the apps offer to hand a conversation to: the workspace and the ones used before."""
        return await agent_folders.offered(self._storage.store, user_id)

    async def child_folders(self, folder: str) -> FolderListing:
        """The folders inside `folder`, to browse to one. Raises FolderError."""
        return await agent_folders.children(folder)

    async def take_back_conversation(self, user_id: str, thread_id: str) -> None:
        await handoffs.take_back(self._storage.store, user_id, thread_id)

    async def _handed_off(
        self, session: Session, handoff: Handoff, message: HumanMessage, said: str
    ) -> AsyncIterator[Event]:
        async for event in self._run_with(session, lambda: self._agent_turn(session, handoff, message, said)):
            yield event

    async def _agent_turn(
        self, session: Session, handoff: Handoff, message: HumanMessage, said: str
    ) -> AsyncIterator[Event]:
        """The agent answers; the message and its reply are added to the conversation."""
        yield ToolStarted(handoff.name, {"folder": handoff.folder})
        try:
            reply = await self._ask_agent(session, handoff, said)
        except HandoffError as e:
            yield Error(str(e))
            return
        yield ToolFinished(handoff.name, f"Replied, working in {handoff.folder}")
        config: RunnableConfig = {"configurable": {"thread_id": session.thread_id}}
        # Written as the agent node's output: the graph reads it as a finished turn, nothing left to run.
        await self._graph.aupdate_state(config, {"messages": [message, AIMessage(reply)]}, as_node="agent")
        yield TextDelta(reply)
        yield Done()

    async def _ask_agent(self, session: Session, handoff: Handoff, said: str) -> str:
        """Raises HandoffError with what went wrong, for the user."""
        agent = next((a for a in await self.agents() if a.server == handoff.server), None)
        if agent is None:
            raise HandoffError(f"{handoff.name} isn't installed or is turned off. /{handoff.command} off goes back.")
        arguments = {"conversation": session.thread_id, "folder": handoff.folder, "message": said}
        try:
            result = await self.mcp.call(agent.server, agent.tool, arguments)
        except (NotConnectedError, ConnectionLostError, MCPError) as e:
            raise HandoffError(f"{handoff.name} couldn't answer: {e}") from e
        if result.is_error:
            raise HandoffError(f"{handoff.name}: {render(result)}")
        return render(result)
