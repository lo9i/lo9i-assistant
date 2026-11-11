"""Devices allowed to use the daemon over the network (browsers on other hosts), and the one-time
codes that pair a new one. Tokens and codes are stored only as SHA-256 hashes, so a copy of the
database doesn't let anyone in.

A device can hold several tokens, one record each: signing in with one of its passkeys
(core/passkeys.py) gives the browser a new one, so the passkey works in every browser it's synced
to without signing the others out. Revoking the device revokes them all."""

import hashlib
import hmac
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from langgraph.store.base import BaseStore

_DEVICES = ("devices",)
_PAIRING = ("device_pairing",)
_PAIRING_KEY = "code"
# No 0/O, 1/I/L: the code is read on one screen and typed on another.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_LENGTH = 8
_PAIRING_LIFETIME = timedelta(minutes=10)
# A device unused this long has to pair again.
UNUSED_LIFETIME = timedelta(days=90)
# Last use is saved at most this often, so requests don't each write to the database.
_TOUCH_EVERY = timedelta(hours=1)


@dataclass
class Device:
    id: str
    name: str
    created_at: str
    last_used_at: str
    last_ip: str


@dataclass
class PairingCode:
    code: str  # As shown, e.g. K7QM-2XPD
    expires_at: str


def new_code() -> str:
    """A random code to read and type, as shown, e.g. K7QM-2XPD."""
    code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    return f"{code[:4]}-{code[4:]}"


def normalized(code: str) -> str:
    """The code as typed, without spaces or dashes and in capitals."""
    return "".join(code.split()).replace("-", "").upper()


async def open_pairing(store: BaseStore, now: datetime) -> PairingCode:
    """A new one-time code, replacing any earlier one."""
    code = new_code()
    expires = (now + _PAIRING_LIFETIME).isoformat()
    await store.aput(_PAIRING, _PAIRING_KEY, {"hash": hashed(normalized(code)), "expires_at": expires})
    return PairingCode(code, expires)


async def take_pairing(store: BaseStore, code: str, now: datetime) -> bool:
    """Whether `code` is the open code and still valid. A right code is used up."""
    item = await store.aget(_PAIRING, _PAIRING_KEY)
    if item is None or now >= datetime.fromisoformat(item.value["expires_at"]):
        return False
    if not hmac.compare_digest(item.value["hash"], hashed(normalized(code))):
        return False
    await store.adelete(_PAIRING, _PAIRING_KEY)
    return True


async def add(store: BaseStore, name: str, ip: str, now: datetime) -> tuple[Device, str]:
    """A new device and its token. The token is returned once and never stored."""
    token = secrets.token_urlsafe(32)
    stamp = now.isoformat()
    device = Device(secrets.token_hex(6), name.strip()[:60] or "Browser", stamp, stamp, ip)
    await store.aput(_DEVICES, hashed(token), asdict(device))
    return device, token


async def add_token(store: BaseStore, device_id: str, ip: str, now: datetime) -> tuple[Device, str] | None:
    """A new token for a device paired before, None once it's revoked. Its tokens unused too long go."""
    tokens = [item for item in await store.asearch(_DEVICES, limit=1000) if item.value["id"] == device_id]
    if not tokens:
        return None
    for item in tokens:
        if now - datetime.fromisoformat(item.value["last_used_at"]) > UNUSED_LIFETIME:
            await store.adelete(_DEVICES, item.key)
    token = secrets.token_urlsafe(32)
    device = Device(**{**tokens[0].value, "last_used_at": now.isoformat(), "last_ip": ip})
    await store.aput(_DEVICES, hashed(token), asdict(device))
    return device, token


async def find(store: BaseStore, token: str, ip: str, now: datetime) -> Device | None:
    """The device a token belongs to, unless it was revoked or unused too long. Records its use."""
    item = await store.aget(_DEVICES, hashed(token))
    if item is None:
        return None
    device = Device(**item.value)
    if now - datetime.fromisoformat(device.last_used_at) > UNUSED_LIFETIME:
        return None
    if now - datetime.fromisoformat(device.last_used_at) > _TOUCH_EVERY or device.last_ip != ip:
        device.last_used_at, device.last_ip = now.isoformat(), ip
        await store.aput(_DEVICES, hashed(token), asdict(device))
    return device


async def list_all(store: BaseStore) -> list[Device]:
    """Most recently used first; a device with several tokens once, as its latest use."""
    latest: dict[str, Device] = {}
    for item in await store.asearch(_DEVICES, limit=1000):
        device = Device(**item.value)
        if device.id not in latest or device.last_used_at > latest[device.id].last_used_at:
            latest[device.id] = device
    return sorted(latest.values(), key=lambda d: d.last_used_at, reverse=True)


async def revoke(store: BaseStore, device_id: str) -> bool:
    """Whether a device with that id existed. Every token it holds goes."""
    tokens = [item for item in await store.asearch(_DEVICES, limit=1000) if item.value["id"] == device_id]
    for item in tokens:
        await store.adelete(_DEVICES, item.key)
    return bool(tokens)


def hashed(secret: str) -> str:
    """How a token or code is stored."""
    return hashlib.sha256(secret.encode()).hexdigest()
