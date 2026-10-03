from assistant.client.daemon_client.repositories import DOWNLOAD_TIMEOUT
from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Skill, SkillError
from assistant.core.agent.skills import SkillSummary

_NOT_FOUND = {404: SkillError}


class SkillsApi:
    """Browsing, editing, updating and deleting skills. Built-in skills can only be read. Installing is
    `client.repositories`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[SkillSummary]:
        return [SkillSummary(**s) for s in await self._transport.request("GET", "/skills")]

    async def get(self, name: str) -> Skill:
        return Skill(**await self._transport.request("GET", f"/skills/{name}", errors=_NOT_FOUND))

    async def update(self, name: str, description: str, instructions: str) -> Skill:
        """Raises SkillError for an unknown or built-in skill, or empty text."""
        body = {"description": description, "instructions": instructions}
        data = await self._transport.request(
            "PUT", f"/skills/{name}", json=body, errors={**_NOT_FOUND, 400: SkillError}
        )
        return Skill(**data)

    async def delete(self, name: str) -> None:
        await self._transport.request("DELETE", f"/skills/{name}", errors=_NOT_FOUND)

    async def update_installed(self, name: str) -> Skill:
        """Install the skill again from its repository. Raises SkillError if it wasn't installed from one."""
        data = await self._transport.request(
            "POST", f"/skills/{name}/update", errors={**_NOT_FOUND, 400: SkillError}, timeout=DOWNLOAD_TIMEOUT
        )
        return Skill(**data)
