from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Language, LanguageError


class LanguageApi:
    """The language of the apps' own text."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self) -> Language:
        return (await self._transport.request("GET", "/settings/language"))["language"]

    async def set(self, language: str) -> Language:
        """Raises LanguageError for an unknown language."""
        body = {"language": language}
        data = await self._transport.request("PUT", "/settings/language", json=body, errors={400: LanguageError})
        return data["language"]
