from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import DoctorPage, StartingContext


class DoctorApi:
    """The daemon's health checks: the latest report, checking today now, and the causes marked as known noise."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> DoctorPage:
        return DoctorPage.model_validate(await self._transport.request("GET", "/doctor"))

    async def context(self) -> StartingContext:
        """What a new conversation's context would be made of now, part by part."""
        return StartingContext.model_validate(await self._transport.request("GET", "/doctor/context"))

    async def check(self) -> DoctorPage:
        """Checks today so far in the background; its report comes with a `doctor` event."""
        return DoctorPage.model_validate(await self._transport.request("POST", "/doctor/check"))

    async def mark_known(self, cause_id: str) -> DoctorPage:
        """The cause is noise: left out from now on."""
        return DoctorPage.model_validate(await self._transport.request("PUT", f"/doctor/known/{cause_id}"))

    async def forget_known(self, cause_id: str) -> DoctorPage:
        """The cause shows again from the next check."""
        return DoctorPage.model_validate(await self._transport.request("DELETE", f"/doctor/known/{cause_id}"))
