from assistant.client.daemon_client.chat import ChatBase
from assistant.core.agent import ConversationError

_NOT_FOUND = {404: ConversationError}


class SessionsMixin(ChatBase):
    """The conversation this client is on. Each client holds its own; the daemon archives one
    that no client is on any more."""

    async def inbox_thread(self, user_id: str) -> str:
        """Move this client to the inbox, which routes each message to its conversation, and return its id."""
        return (await self._transport.request("POST", "/threads/inbox"))["thread_id"]

    async def new_thread(self, user_id: str) -> str:
        """Move this client to a new conversation."""
        return (await self._transport.request("POST", "/threads"))["thread_id"]

    async def resume_thread(self, user_id: str, thread_id: str) -> None:
        """Move this client to an earlier conversation. Raises ConversationError."""
        await self._transport.request("POST", f"/conversations/{thread_id}/resume", errors=_NOT_FOUND)

    async def leave_thread(self) -> None:
        """Close the conversation this client is on without moving to another, as a closed chat tab."""
        await self._transport.request("POST", "/threads/leave")
