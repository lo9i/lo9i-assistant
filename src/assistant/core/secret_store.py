"""Secrets (passwords, OAuth tokens) kept encrypted in the Store, under ("secrets",).

The key is a file outside the database (`settings.secrets_key_path`), readable only by the user,
so a copy of the database alone reveals no secret. Losing the key file loses the secrets: each
account then asks to be connected again.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from langgraph.store.base import BaseStore

_NAMESPACE = ("secrets",)


class SecretError(Exception):
    """A secret can't be read: the key file changed or was lost."""


class SecretBox:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def open(cls, path: Path) -> "SecretBox":
        """Reads the key, creating it on first use (blocking: call it in a thread)."""
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.exists():
            _write_new_key(path)
        return cls(path.read_bytes().strip())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise SecretError("The secret can't be read with this key file.") from e


async def put(store: BaseStore, box: SecretBox, ref: str, value: str) -> None:
    await store.aput(_NAMESPACE, ref, {"value": box.encrypt(value)})


async def get(store: BaseStore, box: SecretBox, ref: str) -> str:
    """The secret, or "" when none is saved. Raises SecretError when it can't be read."""
    item = await store.aget(_NAMESPACE, ref)
    return box.decrypt(item.value["value"]) if item else ""


async def delete(store: BaseStore, ref: str) -> None:
    await store.adelete(_NAMESPACE, ref)


def _write_new_key(path: Path) -> None:
    # Created with the final permissions, so the key is never readable by others, even briefly.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(Fernet.generate_key())
