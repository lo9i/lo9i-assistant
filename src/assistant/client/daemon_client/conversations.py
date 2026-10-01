from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Conversation, ShownMessage


class ConversationsApi:
    """Earlier conversations: the list, and what was said in one. Resuming one is a conversation
    call on the client (`resume_thread`)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def recent(self) -> list[Conversation]:
        """Newest activity first."""
        return [Conversation(**c) for c in await self._transport.request("GET", "/conversations")]

    async def messages(self, thread_id: str) -> list[ShownMessage]:
        return [ShownMessage(**m) for m in await self._transport.request("GET", f"/conversations/{thread_id}/messages")]
