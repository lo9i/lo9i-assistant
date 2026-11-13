"""Uploads no conversation refers to any more: a file pasted and taken off before it was sent, or one a deleted
conversation left behind.

Each upload is saved in a folder named after a random id (core/uploads.py), and whatever refers to it (a message in a
checkpoint, a message the inbox sent on or one held while an update installed, kept in the Store, a step of a task an
agent was sent it in, a plugin's own record of it) writes its path, and so that id. Rather than read each of those
kinds of record, which a new one would be missed from, every value of lo9i's database and of the plugins' databases is
searched for the ids: an upload whose id is written nowhere is one nothing can reach. A database that can't be read
means nothing is called orphaned."""

import os
import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

# A new upload may not be in any record yet: the web app saves a file before the message that carries it is sent.
RECENT_SECONDS = 24 * 3600
_ID = re.compile(r"[0-9a-f]{32}")
# Runs of hex digits, each 32 long window of one an id that may be written there: the byte before an id isn't always a
# separator (a msgpack string's length can read as a digit), and the run then starts before it.
_RUN = re.compile(r"[0-9a-f]{32,}")
_RUN_BYTES = re.compile(rb"[0-9a-f]{32,}")
_DATABASE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
# Read in parts this large, each overlapping the one before by an id's length, so an id across two is found.
_CHUNK = 1 << 20


class UnreadableDatabaseError(Exception):
    """lo9i's database couldn't be read, so which uploads it refers to is unknown."""


def orphaned(uploads: Path, mentioned: set[str], now: float) -> list[Path]:
    """The files under `uploads` older than RECENT_SECONDS whose id isn't in `mentioned`. A file whose path holds no id
    (not one lo9i saved) is never orphaned."""
    found: list[Path] = []
    for folder, _, files in os.walk(uploads):
        for name in files:
            path = Path(folder) / name
            if _orphan(path, path.relative_to(uploads), mentioned, now):
                found.append(path)
    return sorted(found)


def _orphan(path: Path, relative: Path, mentioned: set[str], now: float) -> bool:
    ids = [part for part in relative.parts[:-1] if _ID.fullmatch(part)]
    try:
        old = now - path.lstat().st_mtime > RECENT_SECONDS
    except OSError:
        return False
    return bool(ids) and old and not any(i in mentioned for i in ids)


def mentioned_ids(database: Path, plugin_data: Path) -> set[str]:
    """Every id written in lo9i's database or a plugin's. Raises UnreadableDatabaseError when lo9i's can't be read."""
    try:
        found = set(_ids_in_values(database))
    except sqlite3.Error as e:
        raise UnreadableDatabaseError(str(e)) from e
    for other in plugin_databases(plugin_data):
        found |= _plugin_ids(other)
    return found


def plugin_databases(plugin_data: Path) -> list[Path]:
    """The SQLite databases at the top of each plugin's data folder."""
    if not plugin_data.is_dir():
        return []
    return sorted(
        path
        for folder in plugin_data.iterdir()
        if folder.is_dir() and not folder.is_symlink()
        for path in folder.iterdir()
        if path.is_file() and path.suffix in _DATABASE_SUFFIXES
    )


def _plugin_ids(database: Path) -> set[str]:
    """Read as SQLite, which puts each value together again; one that isn't (encrypted, damaged) as bytes, with what
    SQLite keeps beside it, which still finds what it holds unencrypted."""
    try:
        return set(_ids_in_values(database))
    except sqlite3.Error:
        return {i for path in (database, database.with_name(database.name + "-wal")) for i in _ids_in_bytes(path)}


def _ids_in_values(database: Path) -> Iterator[str]:
    """Read-only, so it never waits on the daemon's writes nor changes the file."""
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            yield from _ids_in_table(connection, table)
    finally:
        connection.close()


def _ids_in_table(connection: sqlite3.Connection, table: str) -> Iterator[str]:
    quoted = table.replace('"', '""')
    for row in connection.execute(f'SELECT * FROM "{quoted}"'):
        for value in row:
            yield from _ids_in(value)


def _ids_in(value: object) -> Iterable[str]:
    if isinstance(value, bytes):
        return (i for run in _RUN_BYTES.findall(value) for i in _windows(run.decode()))
    if isinstance(value, str):
        return (i for run in _RUN.findall(value) for i in _windows(run))
    return ()


def _windows(run: str) -> Iterator[str]:
    return (run[start : start + 32] for start in range(len(run) - 31))


def _ids_in_bytes(path: Path) -> set[str]:
    found: set[str] = set()
    try:
        with path.open("rb") as file:
            tail = b""
            while chunk := file.read(_CHUNK):
                found |= set(_ids_in(tail + chunk))
                tail = chunk[-31:]
    except OSError:
        pass
    return found
