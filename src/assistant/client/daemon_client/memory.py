from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Episode, Fact, MemoryEditError, MemoryNotFoundError, MemorySnapshot

_ERRORS = {404: MemoryNotFoundError, 400: MemoryEditError}


class MemoryApi:
    """What the assistant remembers about the user."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(**await self._transport.request("GET", "/memory"))

    async def set_profile_section(self, section: str, items: list[str]) -> MemorySnapshot:
        body = {"items": items}
        return MemorySnapshot(**await self._transport.request("PUT", f"/memory/profile/{section}", json=body))

    async def facts(self) -> list[Fact]:
        """Every saved fact, newest first."""
        return [Fact(**f) for f in await self._transport.request("GET", "/memory/facts")]

    async def edit_fact(self, fact_id: str, text: str) -> Fact:
        """It gets a new id. Raises MemoryNotFoundError, or MemoryEditError for empty text."""
        body = {"text": text}
        return Fact(**await self._transport.request("PUT", f"/memory/facts/{fact_id}", json=body, errors=_ERRORS))

    async def delete_fact(self, fact_id: str) -> None:
        await self._transport.request("DELETE", f"/memory/facts/{fact_id}", errors=_ERRORS)

    async def episodes(self) -> list[Episode]:
        """Every summary of a past conversation, newest first."""
        return [Episode(**e) for e in await self._transport.request("GET", "/memory/episodes")]

    async def edit_episode(self, episode_id: str, summary: str) -> Episode:
        """It gets a new id. Raises MemoryNotFoundError, or MemoryEditError for empty text."""
        body = {"text": summary}
        path = f"/memory/episodes/{episode_id}"
        return Episode(**await self._transport.request("PUT", path, json=body, errors=_ERRORS))

    async def delete_episode(self, episode_id: str) -> None:
        await self._transport.request("DELETE", f"/memory/episodes/{episode_id}", errors=_ERRORS)
