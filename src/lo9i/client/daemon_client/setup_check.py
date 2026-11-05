from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import SetupCheck, SetupReport


class OlderDaemonError(Exception):
    """The daemon answering runs a version from before the setup check: it needs a restart on this one."""


class SetupCheckApi:
    """The setup check (core/setup_check/): whether lo9i is installed and set up to work, each part with a fix."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def run(self) -> SetupReport:
        """Asks the model's provider whether the key works, so it takes a moment. Raises OlderDaemonError."""
        report = await self._transport.request("GET", "/setup-check", errors={404: OlderDaemonError})
        return SetupReport([SetupCheck(**c) for c in report["checks"]], report["at"])
