from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    Agent,
    AgentFolders,
    Conversation,
    ConversationError,
    ConversationStats,
    FolderError,
    FolderListing,
    Handoff,
    HandoffError,
    ShownMessage,
    SkillError,
)
from assistant.core.events import ApprovalRequired


class ConversationsApi:
    """Earlier conversations: the list, what was said in one, deleting one, and the skills pinned to
    one. Resuming one is a conversation call on the client (`resume_thread`)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def recent(self) -> list[Conversation]:
        """Newest activity first."""
        return [Conversation(**c) for c in await self._transport.request("GET", "/conversations")]

    async def messages(self, thread_id: str) -> list[ShownMessage]:
        return [ShownMessage(**m) for m in await self._transport.request("GET", f"/conversations/{thread_id}/messages")]

    async def stats(self, thread_id: str) -> ConversationStats:
        """Its messages, tokens and tool calls, and when it started and was last written in."""
        return ConversationStats(**await self._transport.request("GET", f"/conversations/{thread_id}/stats"))

    async def pending_approvals(self, thread_id: str) -> list[ApprovalRequired]:
        """What its run stopped to ask and still waits for, whoever started it; answered with `resume`."""
        return [
            ApprovalRequired(**a) for a in await self._transport.request("GET", f"/conversations/{thread_id}/approvals")
        ]

    async def delete(self, thread_id: str) -> None:
        """Raises ConversationError when it doesn't exist, a client is on it or a reply is running."""
        errors = {404: ConversationError, 409: ConversationError}
        await self._transport.request("DELETE", f"/conversations/{thread_id}", errors=errors)

    async def pinned(self, thread_id: str) -> list[str]:
        """The skills pinned to the conversation, in the order they were pinned."""
        return (await self._transport.request("GET", f"/conversations/{thread_id}/pinned"))["skills"]

    async def pin(self, thread_id: str, name: str) -> list[str]:
        """Raises SkillError for an unknown skill. Returns the pinned skills."""
        path = f"/conversations/{thread_id}/pinned/{name}"
        return (await self._transport.request("PUT", path, errors={404: SkillError}))["skills"]

    async def unpin(self, thread_id: str, name: str) -> list[str]:
        """Returns the pinned skills."""
        return (await self._transport.request("DELETE", f"/conversations/{thread_id}/pinned/{name}"))["skills"]

    async def agents(self) -> list[Agent]:
        """The agents installed plugins bring: /<command> hands a conversation to one."""
        return [Agent(**a) for a in await self._transport.request("GET", "/agents")]

    async def agent_folders(self) -> AgentFolders:
        """The folders to offer for /<command>: the workspace and the ones used before."""
        return AgentFolders(**await self._transport.request("GET", "/agents/folders"))

    async def child_folders(self, path: str) -> FolderListing:
        """The folders inside `path`, to browse to one. Raises FolderError."""
        found = await self._transport.request(
            "GET", "/agents/folders/children", params={"path": path}, errors={400: FolderError}
        )
        return FolderListing(**found)

    async def agent(self, thread_id: str) -> Handoff | None:
        """The agent the conversation is handed to; None while the assistant answers."""
        found = (await self._transport.request("GET", f"/conversations/{thread_id}/agent"))["handoff"]
        return Handoff(**found) if found else None

    async def hand_to(self, thread_id: str, command: str, folder: str) -> Handoff:
        """From the next message, the agent answers in `folder`. Raises HandoffError."""
        body = {"command": command, "folder": folder}
        path = f"/conversations/{thread_id}/agent"
        found = await self._transport.request("PUT", path, json=body, errors={400: HandoffError})
        return Handoff(**found["handoff"])

    async def take_back(self, thread_id: str) -> None:
        """The assistant answers again from the next message."""
        await self._transport.request("DELETE", f"/conversations/{thread_id}/agent")

    async def message_agent(self, thread_id: str, text: str) -> None:
        """Passes `text` on to the agent while it works on the conversation's last message; it takes it
        between its steps. Raises HandoffError when it isn't working, or can't take messages while it works."""
        path = f"/conversations/{thread_id}/agent/messages"
        await self._transport.request("POST", path, json={"text": text}, errors={409: HandoffError})

    async def interrupt_agent(self, thread_id: str) -> None:
        """Stops the agent's step in progress; it waits for the next message. Raises HandoffError as
        message_agent does."""
        path = f"/conversations/{thread_id}/agent/interrupt"
        await self._transport.request("POST", path, errors={409: HandoffError})
