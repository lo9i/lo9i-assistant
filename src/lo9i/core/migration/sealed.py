"""A stream sealed with a password: AES-GCM in chunks, its key derived from the password with scrypt, so an export of
any size is written and read without holding it in memory.

The file starts with a header: `_MAGIC`, the salt, scrypt's log2(n), r and p (a byte each) and a nonce prefix. Chunks
follow, each its length (4 bytes, big-endian) and the chunk sealed with a nonce made of the prefix, its number and
whether it's the last, the header as associated data. So a chunk moved, a file cut short or with more after its last
chunk fails to open, as a wrong password does."""

import os
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from lo9i.core.i18n import said
from lo9i.core.migration.errors import MigrationError

_MAGIC = b"lo9i-export\n"
_SALT = 16
_PREFIX = 7
_HEADER = len(_MAGIC) + _SALT + 3 + _PREFIX
_CHUNK = 1 << 20
_TAG = 16
# scrypt with n = 2^17: 128 MiB and a fraction of a second, once per export or import.
_LOG_N, _R, _P = 17, 8, 1
# What a header may ask of scrypt, so a crafted file can't make the import take gigabytes of memory.
_MAX_LOG_N, _MAX_R, _MAX_P = 20, 16, 4


class WrongPasswordError(MigrationError):
    pass


class SealedWriter:
    """Seals what's written to `out`, a chunk at a time. `finish` seals the last chunk: without it the file can't be
    opened."""

    def __init__(self, out: BinaryIO, password: str) -> None:
        salt, self._prefix = os.urandom(_SALT), os.urandom(_PREFIX)
        self._header = _MAGIC + salt + bytes([_LOG_N, _R, _P]) + self._prefix
        self._aead = AESGCM(_key(password, salt, _LOG_N, _R, _P))
        self._out = out
        self._pending = bytearray()
        self._count = 0
        out.write(self._header)

    def write(self, data: bytes) -> int:
        self._pending += data
        # Only past a whole chunk, so the last one is never sealed before `finish`.
        while len(self._pending) > _CHUNK:
            self._seal(bytes(self._pending[:_CHUNK]), last=False)
            del self._pending[:_CHUNK]
        return len(data)

    def finish(self) -> None:
        self._seal(bytes(self._pending), last=True)
        self._pending.clear()

    def _seal(self, chunk: bytes, last: bool) -> None:
        sealed = self._aead.encrypt(_nonce(self._prefix, self._count, last), chunk, self._header)
        self._out.write(len(sealed).to_bytes(4, "big") + sealed)
        self._count += 1


class SealedReader:
    """What a SealedWriter wrote, read back. Opening it opens the first chunk, so a wrong password fails at once
    (WrongPasswordError); a damaged file fails as it's read (MigrationError)."""

    def __init__(self, source: BinaryIO, password: str) -> None:
        self._source = source
        self._header = source.read(_HEADER)
        if len(self._header) < _HEADER or not self._header.startswith(_MAGIC):
            raise MigrationError(said("This file isn't a lo9i export."))
        self._aead = AESGCM(_key(password, *_parameters(self._header)))
        self._prefix = self._header[-_PREFIX:]
        self._count = 0
        self._ended = False
        self._plain = bytearray()
        try:
            self._open_next()
        except MigrationError as e:
            raise WrongPasswordError(said("The password is wrong, or the export is damaged.")) from e

    def read(self, size: int = -1) -> bytes:
        while not self._ended and (size < 0 or len(self._plain) < size):
            self._open_next()
        taken = bytes(self._plain if size < 0 else self._plain[:size])
        del self._plain[: len(taken)]
        return taken

    def _open_next(self) -> None:
        length = int.from_bytes(_exactly(self._source, 4), "big")
        if length > _CHUNK + _TAG:
            raise MigrationError(said("The export is damaged."))
        sealed = _exactly(self._source, length)
        for last in (False, True):
            try:
                self._plain += self._aead.decrypt(_nonce(self._prefix, self._count, last), sealed, self._header)
            except InvalidTag:
                continue
            self._count += 1
            self._ended = last
            if last and self._source.read(1):
                raise MigrationError(said("The export is damaged."))
            return
        raise MigrationError(said("The export is damaged."))


def _parameters(header: bytes) -> tuple[bytes, int, int, int]:
    at = len(_MAGIC)
    log_n, r, p = header[at + _SALT : at + _SALT + 3]
    if not (1 <= log_n <= _MAX_LOG_N and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P):
        raise MigrationError(said("This file isn't a lo9i export."))
    return header[at : at + _SALT], log_n, r, p


def _key(password: str, salt: bytes, log_n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=1 << log_n, r=r, p=p).derive(password.encode())


def _nonce(prefix: bytes, count: int, last: bool) -> bytes:
    return prefix + count.to_bytes(4, "big") + (b"\x01" if last else b"\x00")


def _exactly(source: BinaryIO, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        part = source.read(size - len(data))
        if not part:
            raise MigrationError(said("The export is cut short: copy the whole file again."))
        data += part
    return bytes(data)
