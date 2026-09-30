"""The assistant's name, for clients and the rename tool."""

from assistant.core import identity
from assistant.core.agent.base import ServiceBase
from assistant.core.identity import InvalidNameError

__all__ = ["IdentityMixin", "InvalidNameError"]


class IdentityMixin(ServiceBase):
    async def assistant_name(self) -> str:
        """Empty when the user hasn't named the assistant."""
        return await identity.load_name(self._storage.store)

    async def rename_assistant(self, name: str) -> str:
        """Returns the saved name. It's used from the next message on. Raises InvalidNameError."""
        return await identity.save_name(self._storage.store, name)
