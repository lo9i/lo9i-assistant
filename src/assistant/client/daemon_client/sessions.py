from assistant.client.daemon_client.chat import ChatBase
from assistant.core.agent import Session


class SessionsMixin(ChatBase):
    async def session(self, user_id: str, channel: str) -> Session:
        return Session(**await self._transport.request("GET", f"/sessions/{channel}"))

    async def new_thread(self, user_id: str) -> str:
        return (await self._transport.request("POST", "/threads"))["thread_id"]
