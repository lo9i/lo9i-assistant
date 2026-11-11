"""The setup code: how the first browser pairs where no client runs on the computer itself, as on an appliance
reached only over the network. It works while no device was ever paired here, and never again once one is, however
it was paired.

The code is the text of the file at SETUP_CODE_PATH: an appliance's image writes the one printed on its label there.
Where there's no file, lo9i writes a code of its own there at start, for whoever can read its files."""

import asyncio
import hmac
import logging
import os
from datetime import datetime
from pathlib import Path

from langgraph.store.base import BaseStore

from lo9i.core import devices

logger = logging.getLogger(__name__)

_SETUP = ("device_setup",)
_CLOSED = "closed"
# Shorter codes, from a file written by hand, could be guessed within the pairing limits.
_MIN_LENGTH = 8


async def prepare(store: BaseStore, path: Path, now: datetime) -> None:
    """At start: closes it where a device is paired already (paired before there was a setup code), else writes a
    code to `path` when there's none."""
    if await _closed(store):
        return
    if await devices.list_all(store):
        await close(store, path, now)
        return
    if not await asyncio.to_thread(path.exists):
        await asyncio.to_thread(_write, path, devices.new_code())
        logger.info("Wrote the setup code for the first browser to %s", path)


async def available(store: BaseStore, path: Path) -> bool:
    """Whether a browser can pair with the setup code now."""
    return await _open(store) and bool(await _code(path))


async def take(store: BaseStore, path: Path, code: str, now: datetime) -> bool:
    """Whether `code` is the setup code and it was still open. A right code closes it."""
    expected = await _code(path) if await _open(store) else ""
    typed = devices.normalized(code)
    if not expected or not hmac.compare_digest(devices.hashed(expected), devices.hashed(typed)):
        return False
    await close(store, path, now)
    return True


async def close(store: BaseStore, path: Path, now: datetime) -> None:
    """For good, once a device is paired. Its file goes too where lo9i may delete it; an image's read-only file
    stays, unused."""
    if await _closed(store):
        return
    await store.aput(_SETUP, _CLOSED, {"at": now.isoformat()})
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except OSError as e:
        logger.info("The setup code is used; its file %s stays: %s", path, e)


async def _open(store: BaseStore) -> bool:
    return not await _closed(store) and not await devices.list_all(store)


async def _closed(store: BaseStore) -> bool:
    return await store.aget(_SETUP, _CLOSED) is not None


async def _code(path: Path) -> str:
    """The code the file holds, normalized; "" without a file or with one too short to be safe."""
    try:
        code = devices.normalized(await asyncio.to_thread(path.read_text))
    except (OSError, UnicodeDecodeError):
        return ""
    if len(code) < _MIN_LENGTH:
        logger.warning("The setup code in %s is shorter than %d characters; it isn't used.", path, _MIN_LENGTH)
        return ""
    return code


def _write(path: Path, code: str) -> None:
    """Readable only by lo9i's user."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
            file.write(f"{code}\n")
    except OSError as e:
        logger.warning("Couldn't write the setup code to %s: %s", path, e)
