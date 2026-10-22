from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import HomePage, HomeSection, HomeSectionsError

_ERRORS = {400: HomeSectionsError}


class HomeApi:
    """Home: its sections with their last results, refreshed in the background, and the sections themselves."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> HomePage:
        return HomePage.model_validate(await self._transport.request("GET", "/home"))

    async def refresh(self, force: bool = False) -> HomePage:
        """Unforced, nothing happens while the last refresh is fresh."""
        return HomePage.model_validate(await self._transport.request("POST", "/home/refresh", json={"force": force}))

    async def save_sections(self, sections: list[HomeSection]) -> HomePage:
        """Raises HomeSectionsError."""
        body = {"sections": [s.model_dump() for s in sections]}
        return HomePage.model_validate(
            await self._transport.request("PUT", "/home/sections", json=body, errors=_ERRORS)
        )

    async def reset_sections(self) -> HomePage:
        return HomePage.model_validate(await self._transport.request("DELETE", "/home/sections"))
