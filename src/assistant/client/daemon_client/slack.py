from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import SlackError, SlackStatus

_PATH = "/integrations/slack"


class SlackApi:
    """The daemon's Slack connection: the app manifest, setting its tokens, disconnecting."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def status(self) -> SlackStatus:
        return SlackStatus(**await self._transport.request("GET", _PATH))

    async def manifest(self) -> str:
        return (await self._transport.request("GET", f"{_PATH}/manifest"))["manifest"]

    async def connect(self, app_token: str, bot_token: str, user_token: str) -> SlackStatus:
        tokens = {"app_token": app_token, "bot_token": bot_token, "user_token": user_token}
        return SlackStatus(**await self._transport.request("POST", _PATH, json=tokens, errors={400: SlackError}))

    async def disconnect(self) -> None:
        await self._transport.request("DELETE", _PATH)
