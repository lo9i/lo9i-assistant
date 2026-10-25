from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import DoctorPage


class DoctorApi:
    """The daemon's health checks: the latest report, checking today now, and the causes marked as known noise."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> DoctorPage:
        return DoctorPage.model_validate(await self._transport.request("GET", "/doctor"))

    async def check(self) -> DoctorPage:
        """Checks today so far in the background; its report comes with a `doctor` event."""
        return DoctorPage.model_validate(await self._transport.request("POST", "/doctor/check"))

    async def mark_known(self, cause_id: str) -> DoctorPage:
        """The cause is noise: left out from now on."""
        return DoctorPage.model_validate(await self._transport.request("PUT", f"/doctor/known/{cause_id}"))

    async def forget_known(self, cause_id: str) -> DoctorPage:
        """The cause shows again from the next check."""
        return DoctorPage.model_validate(await self._transport.request("DELETE", f"/doctor/known/{cause_id}"))
