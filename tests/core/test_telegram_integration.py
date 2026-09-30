"""Telegram settings stored in the database: connect, pairing, access and heartbeat."""

import pytest

import assistant.core.integrations.telegram as integration
from assistant.core.agent import InvalidTokenError


@pytest.fixture
def fake_telegram(monkeypatch):
    async def bot_username(token):
        if token != "111:GOOD":
            raise InvalidTokenError("Telegram rejected the token: Unauthorized")
        return "lo9i_bot"

    monkeypatch.setattr(integration, "bot_username", bot_username)


async def test_connect_pair_once_and_disconnect(service, fake_telegram):
    with pytest.raises(InvalidTokenError):
        await service.connect_telegram("bad")
    status = await service.connect_telegram("111:GOOD")
    assert status.connected and status.bot_username == "lo9i_bot" and status.pairing_code
    assert await service.telegram_token() == "111:GOOD"
    assert not await service.pair_telegram_user("hi lo9i-0000", 666, "Stranger")
    assert await service.pair_telegram_user(f"code {status.pairing_code.upper()}", 222, "Ani")
    assert not await service.pair_telegram_user(status.pairing_code, 333, "Other")
    assert await service.telegram_allowed(222) and not await service.telegram_allowed(333)
    await service.disconnect_telegram()
    assert not (await service.telegram_status()).connected and await service.telegram_token() == ""


async def test_heartbeat_marks_the_bot_running(service):
    assert not (await service.telegram_status()).bot_running
    await service.telegram_heartbeat()
    assert (await service.telegram_status()).bot_running


@pytest.mark.live
async def test_telegram_rejects_a_fake_token():
    with pytest.raises(InvalidTokenError, match="Unauthorized"):
        await integration.bot_username("123456:not-a-real-token")
