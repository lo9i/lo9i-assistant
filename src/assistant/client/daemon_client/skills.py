from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Skill, SkillError
from assistant.core.agent.skills import SkillSummary

_NOT_FOUND = {404: SkillError}


class SkillsApi:
    """Browsing and deleting skills."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[SkillSummary]:
        return [SkillSummary(**s) for s in await self._transport.request("GET", "/skills")]

    async def get(self, name: str) -> Skill:
        return Skill(**await self._transport.request("GET", f"/skills/{name}", errors=_NOT_FOUND))

    async def delete(self, name: str) -> None:
        await self._transport.request("DELETE", f"/skills/{name}", errors=_NOT_FOUND)
