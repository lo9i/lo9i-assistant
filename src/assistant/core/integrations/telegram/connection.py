"""Telegram connection settings, stored as one Store record.

The token lives in the database, not in .env, so any gateway (terminal, web) can connect Telegram
through AssistantService. The Telegram adapter in the daemon reads it from here.
"""

import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import httpx
from langgraph.store.base import BaseStore

_NAMESPACE = ("integrations",)
_KEY = "telegram"
# Separate record, so the bot's frequent heartbeat never overwrites token or pairing changes.
_HEARTBEAT_KEY = "telegram_heartbeat"
_API = "https://api.telegram.org"
_PAIRING_MINUTES = 10


class InvalidTokenError(Exception):
    pass


@dataclass
class TelegramUser:
    id: int
    name: str


@dataclass
class TelegramConfig:
    token: str = ""
    bot_username: str = ""
    users: list[TelegramUser] = field(default_factory=list)
    pairing_code: str = ""
    pairing_expires: str = ""

    def pairing_open(self, now: datetime) -> bool:
        return bool(self.pairing_code) and now < datetime.fromisoformat(self.pairing_expires)

    def open_pairing(self, now: datetime) -> None:
        self.pairing_code = f"lo9i-{secrets.randbelow(9000) + 1000}"
        self.pairing_expires = (now + timedelta(minutes=_PAIRING_MINUTES)).isoformat()


async def load(store: BaseStore) -> TelegramConfig:
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return TelegramConfig()
    value = dict(item.value)
    value["users"] = [TelegramUser(**u) for u in value.get("users", [])]
    return TelegramConfig(**value)


async def save(store: BaseStore, config: TelegramConfig) -> None:
    await store.aput(_NAMESPACE, _KEY, asdict(config))


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)


async def bot_username(token: str) -> str:
    """Checks the token with Telegram. Raises InvalidTokenError with Telegram's reason."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            body = (await client.get(f"{_API}/bot{token.strip()}/getMe")).json()
    except (httpx.HTTPError, ValueError) as e:
        raise InvalidTokenError(f"Couldn't reach Telegram: {e}") from e
    if not body.get("ok"):
        raise InvalidTokenError(f"Telegram rejected the token: {body.get('description', 'unknown error')}")
    return body["result"]["username"]


async def beat(store: BaseStore, now: datetime) -> None:
    await store.aput(_NAMESPACE, _HEARTBEAT_KEY, {"at": now.isoformat()})


async def last_beat(store: BaseStore) -> datetime | None:
    item = await store.aget(_NAMESPACE, _HEARTBEAT_KEY)
    return datetime.fromisoformat(item.value["at"]) if item else None
