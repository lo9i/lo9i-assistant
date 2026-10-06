import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.protocol import RestartStatus, StartupError, StartupStatus

# Enabling waits for the user to answer the macOS password dialog.
_PASSWORD_DIALOG = httpx.Timeout(300, connect=5)


class SystemApi:
    """Start at boot (macOS LaunchDaemon), and restarting the daemon."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def startup_status(self) -> StartupStatus:
        return StartupStatus(**await self._transport.request("GET", "/system/startup"))

    async def enable_startup(self) -> StartupStatus:
        """Asks macOS for an administrator password (a system dialog). Raises StartupError."""
        return await self._change_startup("POST")

    async def disable_startup(self) -> StartupStatus:
        return await self._change_startup("DELETE")

    async def restart(self) -> RestartStatus:
        """The daemon restarts once no run is in progress."""
        return RestartStatus(**await self._transport.request("POST", "/system/restart"))

    async def _change_startup(self, method: str) -> StartupStatus:
        data = await self._transport.request(
            method, "/system/startup", errors={400: StartupError}, timeout=_PASSWORD_DIALOG
        )
        return StartupStatus(**data)
