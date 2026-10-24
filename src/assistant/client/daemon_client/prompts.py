from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import PromptEditError, PromptSection, UnknownPromptError

# 400: an empty text, or an edit that can't be written or deleted; 404: not a prompt the user can edit.
_ERRORS = {400: PromptEditError, 404: UnknownPromptError}


class PromptsApi:
    """The system prompt texts the user edits: the persona, the operating instructions, the channel hints."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[PromptSection]:
        return [PromptSection(**p) for p in await self._transport.request("GET", "/settings/prompts")]

    async def save(self, name: str, text: str) -> PromptSection:
        """Used instead of the built-in text; saving the built-in text removes the edit. Raises PromptEditError
        or UnknownPromptError."""
        data = await self._transport.request("PUT", f"/settings/prompts/{name}", json={"text": text}, errors=_ERRORS)
        return PromptSection(**data)

    async def keep(self, name: str) -> PromptSection:
        """Keeps the edit as it is after the built-in text changed (`built_in_changes`). Raises PromptEditError or
        UnknownPromptError."""
        path = f"/settings/prompts/{name}/kept"
        return PromptSection(**await self._transport.request("POST", path, errors=_ERRORS))

    async def reset(self, name: str) -> PromptSection:
        """Back to the built-in text. Raises PromptEditError or UnknownPromptError."""
        return PromptSection(**await self._transport.request("DELETE", f"/settings/prompts/{name}", errors=_ERRORS))
