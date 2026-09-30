"""Connecting Telegram from any gateway, and the checks the Telegram bot relies on."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from assistant.core.agent.base import ServiceBase
from assistant.core.integrations import telegram
from assistant.core.integrations.telegram import InvalidTokenError, TelegramUser

__all__ = ["InvalidTokenError", "TelegramMixin", "TelegramStatus"]

# The bot beats every few seconds; older than this means it isn't running.
_ALIVE = timedelta(seconds=20)


@dataclass
class TelegramStatus:
    """What a setup screen shows. Never includes the token."""

    connected: bool
    bot_running: bool
    bot_username: str
    paired_users: list[str]
    pairing_code: str
    pairing_expires: str


class TelegramMixin(ServiceBase):
    async def telegram_status(self) -> TelegramStatus:
        return await self._telegram_status(await telegram.load(self._storage.store))

    async def connect_telegram(self, token: str) -> TelegramStatus:
        """Check the token, save it, and open pairing. Raises InvalidTokenError."""
        username = await telegram.bot_username(token)
        config = await telegram.load(self._storage.store)
        config.token, config.bot_username = token.strip(), username
        config.open_pairing(datetime.now(UTC))
        await telegram.save(self._storage.store, config)
        return await self._telegram_status(config)

    async def start_telegram_pairing(self) -> TelegramStatus:
        """A new one-time code, to pair another account or replace an expired code."""
        config = await telegram.load(self._storage.store)
        config.open_pairing(datetime.now(UTC))
        await telegram.save(self._storage.store, config)
        return await self._telegram_status(config)

    async def disconnect_telegram(self) -> None:
        await telegram.clear(self._storage.store)

    # Used by the Telegram gateway.

    async def telegram_heartbeat(self) -> None:
        await telegram.beat(self._storage.store, datetime.now(UTC))

    async def telegram_token(self) -> str:
        return (await telegram.load(self._storage.store)).token

    async def telegram_recipients(self) -> list[int]:
        """Paired accounts. Their private chat with the bot has the same id as the account."""
        return [u.id for u in (await telegram.load(self._storage.store)).users]

    async def telegram_allowed(self, user_id: int) -> bool:
        return any(u.id == user_id for u in (await telegram.load(self._storage.store)).users)

    async def pair_telegram_user(self, text: str, user_id: int, name: str) -> bool:
        """Pairs the sender if `text` contains the open pairing code. The code works once."""
        config = await telegram.load(self._storage.store)
        if not config.pairing_open(datetime.now(UTC)) or config.pairing_code.lower() not in text.lower():
            return False
        if not any(u.id == user_id for u in config.users):
            config.users.append(TelegramUser(user_id, name))
        config.pairing_code = config.pairing_expires = ""
        await telegram.save(self._storage.store, config)
        return True

    async def _telegram_status(self, config: telegram.TelegramConfig) -> TelegramStatus:
        beat = await telegram.last_beat(self._storage.store)
        return _status(config, bool(beat) and datetime.now(UTC) - beat < _ALIVE)


def _status(config: telegram.TelegramConfig, bot_running: bool) -> TelegramStatus:
    pairing = config.pairing_open(datetime.now(UTC))
    return TelegramStatus(
        connected=bool(config.token),
        bot_running=bot_running,
        bot_username=config.bot_username,
        paired_users=[u.name for u in config.users],
        pairing_code=config.pairing_code if pairing else "",
        pairing_expires=config.pairing_expires if pairing else "",
    )
