"""SlackSender delivers agent-started messages to the owner's DM with the bot."""

from unittest.mock import MagicMock, create_autospec

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.outbox import DeliveryError
from assistant.gateways.slack.sender import SlackSender


def _client() -> MagicMock:
    client = create_autospec(AsyncWebClient, instance=True)
    client.conversations_open.return_value = {"channel": {"id": "D1"}}
    client.chat_postMessage.return_value = {"ts": "1.0"}
    return client


async def test_sends_to_the_owners_dm():
    client = _client()
    await SlackSender(client, "U1").send("Stretch!")
    assert client.conversations_open.call_args.kwargs["users"] == "U1"
    assert client.chat_postMessage.call_args.kwargs["channel"] == "D1"


async def test_a_slack_error_is_a_delivery_error():
    client = _client()
    client.conversations_open.side_effect = SlackApiError("bad", {"error": "user_not_found"})
    with pytest.raises(DeliveryError, match="user_not_found"):
        await SlackSender(client, "U1").send("hi")
