import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.protocol import (
    Commit,
    HostStatus,
    NoEndingError,
    PendingEnding,
    ShutdownStatus,
    StartupError,
    StartupStatus,
    StopRefusedError,
    UpdateError,
    UpdateStatus,
)

# Enabling waits for the user to answer the macOS password dialog.
_PASSWORD_DIALOG = httpx.Timeout(300, connect=5)
# Checking for an update fetches the repository (up to a minute, daemon/updates.py).
_FETCH = httpx.Timeout(90, connect=5)


class SystemApi:
    """The host the daemon runs on, start at boot (macOS LaunchDaemon), restarting or stopping the daemon, and
    updating it."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def host(self) -> HostStatus:
        return HostStatus(**await self._transport.request("GET", "/system/host"))

    async def startup_status(self) -> StartupStatus:
        return StartupStatus(**await self._transport.request("GET", "/system/startup"))

    async def enable_startup(self) -> StartupStatus:
        """Asks macOS for an administrator password (a system dialog). Raises StartupError."""
        return await self._change_startup("POST")

    async def disable_startup(self) -> StartupStatus:
        return await self._change_startup("DELETE")

    async def reinstall_startup(self) -> StartupStatus:
        """Installs an out-of-date start at boot again (`outdated`), asking macOS for the password. A daemon it
        started restarts once no run is in progress. Raises StartupError."""
        return await self._change_startup("POST", "/system/startup/reinstall")

    async def restart(self) -> ShutdownStatus:
        """The daemon restarts once no run is in progress."""
        return ShutdownStatus(**await self._transport.request("POST", "/system/restart"))

    async def stop(self) -> ShutdownStatus:
        """The daemon stops once no run is in progress. Raises StopRefusedError when its service manager
        would start it again."""
        return ShutdownStatus(**await self._transport.request("POST", "/system/stop", errors={409: StopRefusedError}))

    async def ending(self) -> PendingEnding:
        """The restart or stop waiting for runs to end; `ending` is "" when none is."""
        return PendingEnding(**await self._transport.request("GET", "/system/ending"))

    async def take_back_ending(self) -> PendingEnding:
        """The daemon keeps running. Raises NoEndingError when nothing waits, or it already went ahead."""
        data = await self._transport.request("DELETE", "/system/ending", errors={409: NoEndingError})
        return PendingEnding(**data)

    async def end_now(self) -> int:
        """Cancels the runs the restart or stop waits for, so it goes ahead; returns how many. Raises
        NoEndingError when nothing waits."""
        data = await self._transport.request("POST", "/system/ending/now", errors={409: NoEndingError})
        return data["cancelled"]

    async def update_status(self) -> UpdateStatus:
        """The version it runs and, as of the last check, what's new."""
        return _update(await self._transport.request("GET", "/system/update"))

    async def check_for_update(self) -> UpdateStatus:
        """Reaches the repository to see what's new."""
        return _update(await self._transport.request("POST", "/system/update/check", timeout=_FETCH))

    async def update(self) -> UpdateStatus:
        """Starts installing what's new; the daemon restarts once it's installed. Raises UpdateError when there's
        nothing to install or it can't be installed there."""
        data = await self._transport.request("POST", "/system/update", errors={409: UpdateError}, timeout=_FETCH)
        return _update(data)

    async def _change_startup(self, method: str, path: str = "/system/startup") -> StartupStatus:
        data = await self._transport.request(method, path, errors={400: StartupError}, timeout=_PASSWORD_DIALOG)
        return StartupStatus(**data)


def _update(data: dict) -> UpdateStatus:
    current, new = data.pop("current"), data.pop("new")
    return UpdateStatus(**data, current=Commit(**current) if current else None, new=[Commit(**c) for c in new])
