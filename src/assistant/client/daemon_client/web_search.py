from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import InvalidSearchKeyError, WebSearchStatus

_PATH = "/integrations/web-search"


class WebSearchApi:
    """Web search: the Brave Search API key, tried first when set."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def status(self) -> WebSearchStatus:
        return WebSearchStatus(**await self._transport.request("GET", _PATH))

    async def set_brave_key(self, key: str) -> WebSearchStatus:
        """Raises InvalidSearchKeyError when Brave doesn't accept it."""
        body, errors = {"key": key}, {400: InvalidSearchKeyError}
        return WebSearchStatus(**await self._transport.request("PUT", f"{_PATH}/brave-key", json=body, errors=errors))

    async def remove_brave_key(self) -> WebSearchStatus:
        return WebSearchStatus(**await self._transport.request("DELETE", f"{_PATH}/brave-key"))
