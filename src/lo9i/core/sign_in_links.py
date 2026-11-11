"""Sign-in links: a browser that isn't paired asks for one with the owner's email address, and opening the link
emailed pairs it as a new device. A link works once, within `LIFETIME`, and only on the site it was asked from (the
same host name and port), where the browser's cookie is kept. Tokens are stored only as hashes."""

import secrets
from datetime import datetime, timedelta

from langgraph.store.base import BaseStore

from lo9i.core import devices

LIFETIME = timedelta(minutes=15)
_LINKS = ("sign_in_links",)


async def open_link(store: BaseStore, site: str, now: datetime) -> str:
    """A new link's token for `site` (its origin, e.g. https://lo9i.local:8443). Links expired go."""
    for item in await store.asearch(_LINKS, limit=1000):
        if _expired(item.value, now):
            await store.adelete(_LINKS, item.key)
    token = secrets.token_urlsafe(32)
    await store.aput(_LINKS, devices.hashed(token), {"site": site, "expires_at": (now + LIFETIME).isoformat()})
    return token


async def take(store: BaseStore, token: str, site: str, now: datetime) -> bool:
    """Whether `token` is a link of `site` still valid. A right one is used up; one opened on another site isn't, so
    it still works where it was made for."""
    key = devices.hashed(token)
    item = await store.aget(_LINKS, key)
    if item is None or item.value["site"] != site:
        return False
    await store.adelete(_LINKS, key)
    return not _expired(item.value, now)


def _expired(link: dict, now: datetime) -> bool:
    return now >= datetime.fromisoformat(link["expires_at"])
