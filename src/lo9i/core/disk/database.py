"""lo9i.db's own free space: pages deleted rows left, which SQLite reuses but never gives back to the disk until the
database is rebuilt (VACUUM), and the write-ahead log, which a checkpoint writes into it and empties."""

import sqlite3
from pathlib import Path

# Compacting waits this long for the daemon's own writes, which wait as long for it (core/storage.py's busy timeout).
_BUSY_MILLISECONDS = 5000


def free_space(database: Path) -> int:
    """Bytes compacting would give back: the free pages and the write-ahead log. 0 when the database can't be read."""
    if not database.is_file():
        return 0
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            pages = connection.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        finally:
            connection.close()
    except sqlite3.Error:
        return 0
    return pages * page_size + _size(database.with_name(database.name + "-wal"))


def compact(database: Path) -> None:
    """Rebuilds the database without its free pages, then writes the log into it and empties it. Raises sqlite3.Error
    (busy for longer than the timeout)."""
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        connection.execute(f"PRAGMA busy_timeout={_BUSY_MILLISECONDS}")
        connection.execute("VACUUM")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


def files_size(database: Path) -> int:
    """The database and its log, as they take the disk."""
    return _size(database) + _size(database.with_name(database.name + "-wal"))


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
