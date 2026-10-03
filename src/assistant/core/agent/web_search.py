"""The Brave Search API key, set from any client (Settings → Integrations → Web search, /websearch)."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.internet import brave_key
from assistant.core.internet.brave_key import InvalidSearchKeyError
from assistant.core.secret_store import SecretError

__all__ = ["InvalidSearchKeyError", "WebSearchMixin", "WebSearchStatus"]

# Published on changes: the key lives with the secrets, whose writes clients don't hear about.
_EVENT = "integrations"


@dataclass
class WebSearchStatus:
    """What a settings screen shows. Never includes the key."""

    brave_key_set: bool


class WebSearchMixin(ServiceBase):
    async def web_search_status(self) -> WebSearchStatus:
        try:
            key = await brave_key.load(self._storage.store, self.secrets)
        except SecretError:
            key = ""
        return WebSearchStatus(brave_key_set=bool(key))

    async def set_brave_key(self, key: str) -> WebSearchStatus:
        """Check the key with one search, then save it. Raises InvalidSearchKeyError."""
        key = key.strip()
        await brave_key.check(key)
        await brave_key.save(self._storage.store, self.secrets, key)
        self.bus.publish(_EVENT)
        return WebSearchStatus(brave_key_set=True)

    async def remove_brave_key(self) -> WebSearchStatus:
        await brave_key.clear(self._storage.store)
        self.bus.publish(_EVENT)
        return WebSearchStatus(brave_key_set=False)
