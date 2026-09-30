"""TelegramChat calls the real Bot API: an autospec of telegram.Bot checks every call's arguments."""

from unittest.mock import MagicMock, create_autospec

from telegram.constants import ParseMode

from assistant.gateways.telegram.port import TelegramChat
from telegram import Bot, Message


def _bot() -> MagicMock:
    bot = create_autospec(Bot, instance=True)
    bot.send_message.return_value = create_autospec(Message, instance=True, message_id=7)
    return bot


async def test_send_and_edit_with_markdown():
    bot = _bot()
    chat = TelegramChat(bot, 42)
    assert await chat.send("*hi*", markdown=True) == 7
    await chat.edit(7, "*bye*", markdown=True)
    assert bot.send_message.call_args.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2
    edit = bot.edit_message_text.call_args
    assert edit.kwargs["chat_id"] == 42 and edit.kwargs["message_id"] == 7
    assert edit.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2


async def test_plain_edit():
    bot = _bot()
    await TelegramChat(bot, 42).edit(7, "plain")
    assert bot.edit_message_text.call_args.args == ("plain",)
