from assistant.client.daemon_client.chat import ChatBase
from assistant.core.agent import ConversationError

_NOT_FOUND = {404: ConversationError}


class SessionsMixin(ChatBase):
    """The conversation this client is on. Each client holds its own; the daemon archives one
    that no client is on any more."""

    async def home_thread(self, user_id: str) -> str:
        """Move this client to the home conversation and return its id."""
        return (await self._transport.request("POST", "/threads/home"))["thread_id"]

    async def new_thread(self, user_id: str) -> str:
        """Move this client to a new side conversation."""
        return (await self._transport.request("POST", "/threads"))["thread_id"]

    async def resume_thread(self, user_id: str, thread_id: str) -> None:
        """Move this client to an earlier conversation. Raises ConversationError."""
        await self._transport.request("POST", f"/conversations/{thread_id}/resume", errors=_NOT_FOUND)
