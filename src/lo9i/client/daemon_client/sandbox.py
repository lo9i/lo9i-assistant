from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import SandboxStatus, SandboxUnavailableError

_PATH = "/settings/bash-sandbox"


class SandboxApi:
    """The bash sandbox: whether commands run in a container, and whether one can run here."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def status(self) -> SandboxStatus:
        return SandboxStatus(**await self._transport.request("GET", _PATH))

    async def set_enabled(self, enabled: bool) -> SandboxStatus:
        """Raises SandboxUnavailableError when it can't be turned on, saying why."""
        body, errors = {"enabled": enabled}, {400: SandboxUnavailableError}
        return SandboxStatus(**await self._transport.request("PUT", _PATH, json=body, errors=errors))
