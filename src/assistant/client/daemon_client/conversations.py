from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Conversation, ConversationError, ShownMessage, SkillError


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
