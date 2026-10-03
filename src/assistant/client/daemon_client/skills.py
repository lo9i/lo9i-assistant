import builtins

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import FoundSkill, Skill, SkillError
from assistant.core.agent.skills import SkillSummary

_NOT_FOUND = {404: SkillError}


class SkillsApi:
    """Browsing, editing, deleting and installing skills. Built-in skills can only be read."""

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

    async def browse(self, url: str) -> builtins.list[FoundSkill]:
        """The skills a git repository offers. Raises SkillError if it can't be read or has none."""
        data = await self._transport.request("POST", "/skills/browse", json={"url": url}, errors={400: SkillError})
        return [FoundSkill(**s) for s in data]

    async def install(self, url: str, names: builtins.list[str]) -> builtins.list[Skill]:
        """Raises SkillError if the repository can't be read, lacks a skill, or a name is taken."""
        body = {"url": url, "names": names}
        data = await self._transport.request("POST", "/skills/install", json=body, errors={400: SkillError})
        return [Skill(**s) for s in data]

    async def update_installed(self, name: str) -> Skill:
        """Install the skill again from its repository. Raises SkillError if it wasn't installed from one."""
        data = await self._transport.request("POST", f"/skills/{name}/update", errors={**_NOT_FOUND, 400: SkillError})
        return Skill(**data)
