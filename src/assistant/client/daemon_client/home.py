from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import ConversationError, HomePage, HomePinError, HomeSection, HomeSectionsError

_ERRORS = {400: HomeSectionsError}
_PIN_ERRORS = {400: HomePinError, 404: ConversationError}


class HomeApi:
    """Home: its sections with their last results, refreshed in the background, the sections themselves, and the
    conversations pinned to it."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> HomePage:
        return HomePage.model_validate(await self._transport.request("GET", "/home"))

    async def refresh(self, force: bool = False) -> HomePage:
        """Unforced, nothing happens while the last refresh is fresh."""
        return HomePage.model_validate(await self._transport.request("POST", "/home/refresh", json={"force": force}))

    async def watch(self) -> None:
        """This client shows Home: the daemon keeps it current until `unwatch` or until the client disconnects."""
        await self._transport.request("PUT", "/home/watch")

    async def unwatch(self) -> None:
        await self._transport.request("DELETE", "/home/watch")

    async def save_sections(self, sections: list[HomeSection]) -> HomePage:
        """Raises HomeSectionsError."""
        body = {"sections": [s.model_dump() for s in sections]}
        return HomePage.model_validate(
            await self._transport.request("PUT", "/home/sections", json=body, errors=_ERRORS)
        )

    async def reset_sections(self) -> HomePage:
        return HomePage.model_validate(await self._transport.request("DELETE", "/home/sections"))

    async def pins(self) -> list[str]:
        """The conversations pinned to Home, the first pinned first."""
        return (await self._transport.request("GET", "/home/pins"))["threads"]

    async def pin(self, thread_id: str) -> list[str]:
        """Raises ConversationError for an unknown conversation, HomePinError for the inbox."""
        pinned = await self._transport.request("PUT", f"/home/pins/{thread_id}", errors=_PIN_ERRORS)
        return pinned["threads"]

    async def unpin(self, thread_id: str) -> list[str]:
        return (await self._transport.request("DELETE", f"/home/pins/{thread_id}"))["threads"]
