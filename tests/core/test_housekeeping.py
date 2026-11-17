"""Housekeeping (core/housekeeping.py): old tool outputs leave the search index, old uploads nothing refers to go,
and the empty databases `lo9i clean` offers; what's said and what's referred to stay."""

import os
import sqlite3
from pathlib import Path

import aiosqlite

from lo9i.core import housekeeping
from lo9i.core.conversation.search import MessageIndex
from lo9i.core.disk import Places
from lo9i.core.disk.backups import empty_databases

NOW = 2_000_000_000.0
DAY = 24 * 3600
ID = "0123456789abcdef0123456789abcdef"
OTHER_ID = "fedcba9876543210fedcba9876543210"
NEW_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


async def test_tool_outputs_older_than_the_cutoff_are_forgotten_and_messages_stay(tmp_path: Path) -> None:
    async with aiosqlite.connect(tmp_path / "lo9i.db", isolation_level=None) as conn:
        index = MessageIndex(conn)
        await index.setup()
        rows = [("old page", "2026-01-02 10:00"), ("new page", "2026-06-01 10:00"), ("undated page", "")]
        await conn.executemany(
            "INSERT INTO tool_output_search (text, user_id, thread_id, tool, at) VALUES (?, 'u', 't', 'fetch', ?)", rows
        )
        await conn.execute(
            "INSERT INTO message_search (text, user_id, thread_id, role, at) VALUES "
            "('hi', 'u', 't', 'user', '2026-01-02 10:00')"
        )
        assert await index.old_tool_outputs("2026-03-01") == len("old page")
        assert await index.forget_tool_outputs("2026-03-01") == 1
        async with conn.execute("SELECT text FROM tool_output_search ORDER BY rowid") as cursor:
            assert [r[0] for r in await cursor.fetchall()] == ["new page", "undated page"]
        assert [f.thread_id for f in await index.search("u", "hi", 5)] == ["t"]


def _places(home: Path) -> Places:
    return Places(home / "lo9i.db", (), home / "mcp", home / "data", home / "b", home / "uploads", home / "logs", ())


def _upload(uploads: Path, upload_id: str, age_days: int) -> Path:
    path = uploads / upload_id / "file.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * 100)
    os.utime(path, (NOW - age_days * DAY, NOW - age_days * DAY))
    return path


def test_only_old_uploads_nothing_refers_to_are_planned(tmp_path: Path) -> None:
    places = _places(tmp_path)
    with sqlite3.connect(places.database) as db:
        db.execute("CREATE TABLE t (v)")
        db.execute("INSERT INTO t VALUES (?)", (f"{ID}/file.png",))
    referenced = _upload(places.uploads, ID, 200)
    orphan = _upload(places.uploads, OTHER_ID, housekeeping.UPLOADS_KEEP_DAYS + 1)
    recent = _upload(places.uploads, NEW_ID, 10)
    planned = [Path(i.path) for i in housekeeping.plan([], places, NOW, may_compact=False)]
    assert planned == [orphan]
    assert referenced.exists() and recent.exists()


def test_empty_databases_are_found_but_not_inside_a_profile_or_with_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "notes" / "profile" / "cache").mkdir(parents=True)
    stray, plugin_empty = data / "*.db", data / "notes" / "empty.db"
    for path in (stray, plugin_empty, data / "notes" / "profile" / "cache" / "cache.db"):
        path.write_bytes(b"")
    (data / "notes" / "notes.db").write_bytes(b"SQLite format 3\0")
    assert empty_databases(data) == sorted([stray, plugin_empty])


def test_outputs_before_is_ninety_local_days_back() -> None:
    assert housekeeping.outputs_before(NOW) < housekeeping.outputs_before(NOW + 2 * DAY)
    assert len(housekeeping.outputs_before(NOW)) == len("2026-01-02")
