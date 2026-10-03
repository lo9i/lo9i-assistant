"""Accounts the user connected to services, per kind ("email" now). Each is one Store record under
("accounts", kind) holding its settings; its secret (password, token) is kept apart, encrypted
(core/secret_store.py). One account of each kind is the default, which tools use when none is named.
"""

import secrets
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.secret_store import SecretBox

Status = Literal["ok", "needs_sign_in"]

_SCAN_LIMIT = 1000


@dataclass
class Account:
    id: str
    kind: str
    # What the user calls it ("Personal", "Work").
    label: str
    # What identifies it to other people, such as an email address.
    handle: str
    settings: dict[str, Any] = field(default_factory=dict)
    default: bool = False
    status: Status = "ok"
    # Why it needs signing in again, for the user.
    problem: str = ""


def new_id() -> str:
    return secrets.token_hex(4)


async def list_kind(store: BaseStore, kind: str) -> list[Account]:
    """The default first, then by label."""
    items = await store.asearch(_namespace(kind), limit=_SCAN_LIMIT)
    found = [Account(**item.value) for item in items]
    return sorted(found, key=lambda a: (not a.default, a.label.lower()))


async def get(store: BaseStore, kind: str, account_id: str) -> Account | None:
    item = await store.aget(_namespace(kind), account_id)
    return Account(**item.value) if item else None


async def find(store: BaseStore, kind: str, name: str) -> Account | None:
    """The account called `name` (its id, label or handle, any case), or the default for ""."""
    listed = await list_kind(store, kind)
    wanted = name.strip().lower()
    if not wanted:
        return next((a for a in listed if a.default), None)
    return next((a for a in listed if wanted in {a.id, a.label.lower(), a.handle.lower()}), None)


async def save(store: BaseStore, account: Account) -> None:
    """The first account of a kind becomes its default."""
    if not account.default and not any(a.default for a in await list_kind(store, account.kind) if a.id != account.id):
        account.default = True
    await store.aput(_namespace(account.kind), account.id, asdict(account))


async def make_default(store: BaseStore, account: Account) -> None:
    for other in await list_kind(store, account.kind):
        if other.default != (other.id == account.id):
            other.default = other.id == account.id
            await store.aput(_namespace(other.kind), other.id, asdict(other))


async def remove(store: BaseStore, account: Account) -> None:
    """Removes the account and its secret. Another account becomes the default if it was."""
    await store.adelete(_namespace(account.kind), account.id)
    await secret_store.delete(store, _secret_ref(account))
    rest = await list_kind(store, account.kind)
    if account.default and rest:
        await make_default(store, rest[0])


async def set_secret(store: BaseStore, box: SecretBox, account: Account, value: str) -> None:
    await secret_store.put(store, box, _secret_ref(account), value)


async def secret(store: BaseStore, box: SecretBox, account: Account) -> str:
    """Raises SecretError when it can't be read."""
    return await secret_store.get(store, box, _secret_ref(account))


def _namespace(kind: str) -> tuple[str, ...]:
    return ("accounts", kind)


def _secret_ref(account: Account) -> str:
    return f"{account.kind}:{account.id}"
