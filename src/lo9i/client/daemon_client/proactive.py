from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import LoopNotFoundError, LoopStatus, ProactivePage, ProactiveSettings
from lo9i.core.proactive.schedule import Work


class ProactiveApi:
    """The assistant's own initiative: the morning briefing, the nightly and weekly reviews and their settings, the
    open loops and the kinds of suggestion muted. A `proactive` event says one of them changed."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> ProactivePage:
        return ProactivePage.model_validate(await self._transport.request("GET", "/proactive"))

    async def save_settings(self, wanted: ProactiveSettings) -> ProactivePage:
        body = wanted.model_dump()
        return ProactivePage.model_validate(await self._transport.request("PUT", "/proactive/settings", json=body))

    async def run(self, work: Work) -> ProactivePage:
        """Writes the briefing (and sends it) or a review now, in the background."""
        return ProactivePage.model_validate(await self._transport.request("POST", f"/proactive/run/{work}"))

    async def close_loop(self, loop_id: str, status: LoopStatus, stop_suggesting: bool = False) -> ProactivePage:
        """Raises LoopNotFoundError."""
        body = {"status": status, "stop_suggesting": stop_suggesting}
        found = await self._transport.request(
            "POST", f"/proactive/loops/{loop_id}", json=body, errors={404: LoopNotFoundError}
        )
        return ProactivePage.model_validate(found)

    async def mute(self, kind: str, muted: bool = True) -> ProactivePage:
        body = {"kind": kind, "muted": muted}
        return ProactivePage.model_validate(await self._transport.request("POST", "/proactive/muted", json=body))
