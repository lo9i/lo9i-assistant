"""Scheduled jobs' approval requests in Telegram: shown with job buttons, answered back to the run."""

from unittest.mock import MagicMock, create_autospec

import pytest

from assistant.core.outbox import DeliveryError
from assistant.gateways.chat.approvals import parse_decision, parse_job_decision
from assistant.gateways.telegram.approvals import TelegramApprovals
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


async def test_requests_go_to_every_paired_account_with_job_buttons():
    bot = _bot()
    request = {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}
    await TelegramApprovals(bot, _Service([11])).forward("i1", "The job cleanup", request)
    call = bot.send_message.call_args
    assert call.args[0] == 11 and call.args[1].startswith("The job cleanup is waiting for you.")
    buttons = [b.callback_data for b in call.kwargs["reply_markup"].inline_keyboard[0]]
    assert buttons == ["ja:i1", "jr:i1"]


async def test_no_paired_account_is_a_delivery_error():
    with pytest.raises(DeliveryError):
        await TelegramApprovals(_bot(), _Service([])).forward("i1", "The job x", {})


def test_job_buttons_and_chat_buttons_are_told_apart():
    assert parse_job_decision("ja:i1", "Telegram") == ("i1", {"approved": True, "reason": None})
    assert parse_job_decision("jr:i1", "Telegram") == ("i1", {"approved": False, "reason": "rejected in Telegram"})
    assert parse_job_decision("a:i1", "Telegram") is None and parse_decision("ja:i1", "Telegram") is None
