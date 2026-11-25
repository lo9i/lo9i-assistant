from lo9i.client.daemon_client.setup_check import OlderDaemonError
from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import SetupCheck, SetupReport


class SecurityApi:
    """The security audit (core/security_audit/): how exposed lo9i is, each part with a fix."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def audit(self) -> SetupReport:
        """Raises OlderDaemonError when the daemon runs a version from before the audit."""
        report = await self._transport.request("GET", "/security-audit", errors={404: OlderDaemonError})
        return SetupReport([SetupCheck(**c) for c in report["checks"]], report["at"])
