"""TelegramSender delivers agent-started messages to every paired account."""

from unittest.mock import MagicMock, create_autospec

import pytest
from telegram.error import NetworkError

from assistant.core.outbox import DeliveryError
from assistant.gateways.telegram.sender import TelegramSender
from telegram import Bot, Message


class _Service:
    def __init__(self, recipients: list[int]) -> None:
        self._recipients = recipients

    async def telegram_recipients(self) -> list[int]:
        return self._recipients


def _bot() -> MagicMock:
    bot = create_autospec(Bot, instance=True)
    bot.send_message.return_value = create_autospec(Message, instance=True, message_id=1)
    return bot


def _sender(bot: MagicMock, recipients: list[int]) -> TelegramSender:
    return TelegramSender(bot, _Service(recipients))


async def test_sends_to_every_paired_account():
    bot = _bot()
    await _sender(bot, [11, 22]).send("Stretch!")
    assert [c.args[0] for c in bot.send_message.call_args_list] == [11, 22]


async def test_no_paired_account_or_a_telegram_error_is_a_delivery_error():
    with pytest.raises(DeliveryError, match="paired"):
        await _sender(_bot(), []).send("hi")
    bot = _bot()
    bot.send_message.side_effect = NetworkError("down")
    with pytest.raises(DeliveryError, match="down"):
        await _sender(bot, [11]).send("hi")
