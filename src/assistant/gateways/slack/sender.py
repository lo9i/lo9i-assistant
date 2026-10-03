"""Delivers messages the agent starts (send_message) to the owner's DM with the bot."""

from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.outbox import DeliveryError
from assistant.gateways.chat.split import split_text
from assistant.gateways.slack.port import LIMITS, SlackChat


class SlackSender:
    """Registered in the service's outbox while the adapter is connected (bot.py)."""

    def __init__(self, client: AsyncWebClient, owner_id: str) -> None:
        self._client = client
        self._owner_id = owner_id

    async def send(self, text: str) -> None:
        try:
            chat = SlackChat(self._client, await self._dm())
            for part in split_text(text, LIMITS.chunk):
                await chat.send(part, markdown=True)
        except (SlackApiError, SlackClientError, OSError) as e:
            raise DeliveryError(f"Slack didn't take the message: {e}") from e

    async def _dm(self) -> str:
        channel = (await self._client.conversations_open(users=self._owner_id)).get("channel") or {}
        return str(channel["id"])
