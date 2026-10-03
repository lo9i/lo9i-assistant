"""TelegramChat calls the real Bot API: an autospec of telegram.Bot checks every call's arguments."""

from unittest.mock import MagicMock, create_autospec

from telegram.constants import ParseMode

from assistant.gateways.telegram.formatting import CHUNK
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


async def test_long_text_is_split_with_the_buttons_on_the_last_part():
    bot = _bot()
    command = "\n".join(f"echo line {i}" for i in range(800))  # a bash command over 4096 characters
    await TelegramChat(bot, 42).send(command, buttons=[("Approve", "a:1"), ("Reject", "r:1")])
    sent = bot.send_message.call_args_list
    assert len(sent) > 1 and all(len(c.args[1]) <= CHUNK for c in sent)
    assert "\n".join(c.args[1] for c in sent) == command
    assert [c.kwargs["reply_markup"] is not None for c in sent] == [False] * (len(sent) - 1) + [True]
