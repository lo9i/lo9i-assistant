"""The old computer's paths, where lo9i keeps them as data, changed to this computer's on import: lo9i's Python and uv,
which plugins' commands were filled in with (core/mcp/install.py), the data home, and the user's home folder, under
which conversations keep the folders handed to coding agents and imported skills their sources. Only in
home.WITH_PATHS: the user's own files, plugins' code and conversations' checkpoints stay as they are. Blocking: run in
a thread."""

import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from lo9i.core.migration import home as contents
from lo9i.core.migration.export import is_sqlite

logger = logging.getLogger(__name__)

# Text files larger than this aren't configuration: left as they are.
_MAX_TEXT_BYTES = 4 << 20
# Logs of what happened (a coding task's steps) say where it happened.
_LOGS = ".log"


class Moved:
    """Changes each old path to the new one where it stands alone or starts a longer path: `/Users/me` in
    `/Users/me/x`, never in `/Users/me2`. `pairs` go from the most specific: the first that matches at a place wins."""

    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        self.olds = [old for old, _ in pairs]
        self._new = dict(pairs)
        self._pattern = re.compile("|".join(rf"{re.escape(old)}(?![\w.-])" for old in self.olds)) if pairs else None

    def __call__(self, text: str | None) -> str | None:
        if text is None or self._pattern is None:
            return text
        return self._pattern.sub(lambda m: self._new[m.group(0)], text)

    def __bool__(self) -> bool:
        return self._pattern is not None


def rewrite(home: Path, moved: Moved) -> int:
    """Rewrites the paths in `home`'s entries that hold them; returns how many files changed."""
    if not moved:
        return 0
    changed = 0
    for path in _files(home):
        try:
            changed += _rewrite_database(path, moved) if is_sqlite(path) else _rewrite_text(path, moved)
        except (OSError, sqlite3.Error) as e:
            logger.warning("Couldn't move the paths in %s to this computer's: %s", path, e)
    return changed


def _files(home: Path) -> Iterator[Path]:
    for name in contents.WITH_PATHS:
        top = home / name
        if top.is_file() and not top.is_symlink():
            yield top
        elif top.is_dir() and not top.is_symlink():
            yield from (p for p in sorted(top.rglob("*")) if p.is_file() and not p.is_symlink())


def _rewrite_text(path: Path, moved: Moved) -> int:
    if path.suffix == _LOGS or path.stat().st_size > _MAX_TEXT_BYTES:
        return 0
    data = path.read_bytes()
    if b"\x00" in data or not any(old.encode() in data for old in moved.olds):
        return 0
    try:
        text = data.decode()
    except UnicodeDecodeError:
        return 0
    if (new := moved(text)) == text or new is None:
        return 0
    path.write_text(new, encoding="utf-8")
    return 1


def _rewrite_database(path: Path, moved: Moved) -> int:
    with closing(sqlite3.connect(path)) as db:
        db.create_function("lo9i_moved", 1, moved, deterministic=True)
        changed = sum(_rewrite_table(db, table, moved.olds) for table in _tables(db, path.name))
        db.commit()
    return 1 if changed else 0


def _tables(db: sqlite3.Connection, name: str) -> list[str]:
    """Ordinary tables: not virtual ones (full-text search) or the tables they keep their index in, which their own
    triggers keep up; not lo9i.db's checkpoints."""
    rows = db.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'").fetchall()
    virtual = [table for table, sql in rows if (sql or "").upper().startswith("CREATE VIRTUAL")]
    left_out = contents.CHECKPOINTS if name == contents.DATABASE else frozenset()
    return [
        table
        for table, _ in rows
        if table not in virtual
        and table not in left_out
        and not table.startswith("sqlite_")
        and not any(table.startswith(f"{v}_") for v in virtual)
    ]


def _rewrite_table(db: sqlite3.Connection, table: str, olds: list[str]) -> int:
    changed = 0
    for column in [row[1] for row in db.execute(f"PRAGMA table_info({_quoted(table)})")]:
        c = _quoted(column)
        holds = " OR ".join(f"instr({c}, ?) > 0" for _ in olds)
        query = f"UPDATE {_quoted(table)} SET {c} = lo9i_moved({c}) WHERE typeof({c}) = 'text' AND ({holds})"
        try:
            changed += db.execute(query, olds).rowcount
        except sqlite3.IntegrityError as e:
            logger.warning("Left the paths in %s.%s as they were: %s", table, column, e)
    return changed


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
