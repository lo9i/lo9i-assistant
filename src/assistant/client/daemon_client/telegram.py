from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import InvalidTokenError, TelegramStatus

_PATH = "/integrations/telegram"


class TelegramApi:
    """The daemon's Telegram bot: setting its token, pairing accounts, disconnecting."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def status(self) -> TelegramStatus:
        return TelegramStatus(**await self._transport.request("GET", _PATH))

    async def connect(self, token: str) -> TelegramStatus:
        data = await self._transport.request("POST", _PATH, json={"token": token}, errors={400: InvalidTokenError})
        return TelegramStatus(**data)

    async def start_pairing(self) -> TelegramStatus:
        return TelegramStatus(**await self._transport.request("POST", f"{_PATH}/pairing"))

    async def disconnect(self) -> None:
        await self._transport.request("DELETE", _PATH)
