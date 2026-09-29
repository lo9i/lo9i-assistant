from uuid import uuid4

from assistant.core.agent.base import ServiceBase
from assistant.core.agent.session import Session


class ThreadsMixin(ServiceBase):
    """The user's active conversation, shared by every channel."""

    async def session(self, user_id: str, channel: str) -> Session:
        item = await self._storage.store.aget(_namespace(user_id), "active")
        thread_id = item.value["thread_id"] if item else await self.new_thread(user_id)
        return Session(user_id=user_id, channel=channel, thread_id=thread_id)

    async def new_thread(self, user_id: str) -> str:
        thread_id = f"{user_id}:{uuid4().hex[:12]}"
        await self._storage.store.aput(_namespace(user_id), "active", {"thread_id": thread_id})
        return thread_id


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("threads", user_id)
