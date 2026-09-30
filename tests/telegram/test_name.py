"""The bot's Telegram display name follows the assistant's name."""

from unittest.mock import MagicMock, create_autospec

from telegram.error import NetworkError

from assistant.gateways.telegram.name import BotName
from telegram import Bot


class _Service:
    def __init__(self) -> None:
        self.name = "Max"

    async def assistant_name(self) -> str:
        return self.name


def _bot() -> MagicMock:
    return create_autospec(Bot, instance=True)


async def test_sets_the_name_only_when_it_changes():
    service, bot = _Service(), _bot()
    name = BotName(service)
    await name.apply(bot)
    await name.apply(bot)
    service.name = "Ada"
    await name.apply(bot)
    assert [c.args for c in bot.set_my_name.call_args_list] == [("Max",), ("Ada",)]
    name.forget()  # a new bot
    await name.apply(bot)
    assert bot.set_my_name.call_count == 3


async def test_a_telegram_error_is_retried_at_the_next_change():
    bot = _bot()
    bot.set_my_name.side_effect = NetworkError("down")
    name = BotName(_Service())
    await name.apply(bot)
    bot.set_my_name.side_effect = None
    await name.apply(bot)
    assert bot.set_my_name.call_count == 2
