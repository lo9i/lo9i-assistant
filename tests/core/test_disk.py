"""Disk use (core/disk/): how much each category takes, and what cleaning picks, never what lo9i still needs."""

import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lo9i.core.disk import Places, build, clean
from lo9i.core.disk.caches import TEMPORARY_SECONDS, caches
from lo9i.core.disk.logs import old_logs
from lo9i.core.disk.orphans import RECENT_SECONDS, mentioned_ids, orphaned
from lo9i.core.disk.sizes import Sizes
from lo9i.core.mcp.downloads import DownloadsFolder, parse

NOW = 2_000_000_000.0
OLD = NOW - 2 * RECENT_SECONDS
ID = "0123456789abcdef0123456789abcdef"
OTHER_ID = "fedcba9876543210fedcba9876543210"


def _places(home: Path) -> Places:
    return Places(
        database=home / "lo9i.db",
        models=(home / "models",),
        plugins=home / "mcp",
        plugin_data=home / "data",
        browsers=home / "browsers",
        uploads=home / "uploads",
        logs=home / "logs",
        workspaces=(home / "workspace",),
    )


def _file(path: Path, size: int = 10_000, modified: float = OLD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (modified, modified))
    return path


def _taken(*paths: Path) -> int:
    return sum(p.stat().st_blocks * 512 for p in paths)


def _database(path: Path, *values: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS t (value)")
        db.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
        db.commit()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / ".lo9i"


def _sizes(report) -> dict[str, int]:
    return {c.name: c.bytes for c in report.categories}


def test_each_category_counts_its_own_folder_and_the_rest_is_other(home: Path):
    places = _places(home)
    _database(places.database)
    model = _file(home / "models" / "whisper.bin")
    plugin = _file(home / "mcp" / "youtube" / "server.py")
    upload = _file(home / "uploads" / ID / "photo.png")
    loose = _file(home / "cli_history")
    report = build(places, [], [], NOW)
    sizes = _sizes(report)
    assert sizes["models"] == _taken(model) and sizes["plugins"] == _taken(plugin)
    assert sizes["uploads"] == _taken(upload) and sizes["other"] == _taken(loose)
    assert sizes["database"] == _taken(places.database)
    assert report.total == sum(sizes.values())


def test_a_category_inside_another_folder_is_counted_once(home: Path):
    places = _places(home)
    places = Places(**{**places.__dict__, "logs": home / "workspace" / "logs"})
    log = _file(places.logs / "daemon.log")
    work = _file(home / "workspace" / "notes.md")
    sizes = _sizes(build(places, [], [], NOW))
    assert sizes["logs"] == _taken(log) and sizes["workspace"] == _taken(work)


def test_a_file_with_two_links_counts_once(tmp_path: Path):
    first = _file(tmp_path / "a" / "file")
    os.link(first, tmp_path / "a" / "again")
    assert Sizes().of(tmp_path / "a") == _taken(first)


def test_old_logs_are_the_rotated_parts_and_the_output_from_before_the_logs_moved(home: Path):
    logs = home / "logs"
    for name in ("daemon.log", "errors.log", "output.log", "daemon.log.1", "errors.log.3", "output.log.1"):
        _file(logs / name)
    legacy = _file(home / "daemon.log")
    found = old_logs(logs, home)
    assert sorted(p.name for p in found if p.parent == logs) == ["daemon.log.1", "errors.log.3", "output.log.1"]
    assert legacy in found


def test_where_the_logs_folder_is_the_home_its_daemon_log_is_the_live_one(home: Path):
    _file(home / "daemon.log")
    assert old_logs(home, home) == []


def test_old_copies_of_the_data_are_cleaned_and_never_the_live_database(home: Path):
    places = _places(home)
    _database(places.database)
    for sidecar in ("-wal", "-shm"):
        _file(home / f"lo9i.db{sidecar}")
    copies = [_file(home / "lo9i-before-accounts.db"), _file(home / "lo9i-before-accounts.db-shm")]
    copies.append(_file(home / "facts-backup-2026-10-25.json"))
    aside = _file(home.parent / ".lo9i-before-import-20261101-120000" / "lo9i.db")
    report = build(places, [], [], NOW)
    cleaned = {Path(i.path) for i in report.items if i.category == "backups"}
    assert cleaned == set(copies)
    assert not cleaned & set(places.database_files())
    # The folder an import set aside is counted, never cleaned: it's the whole of the data it replaced.
    assert _sizes(report)["backups"] == _taken(*copies, aside)


def test_an_upload_no_record_mentions_is_orphaned(home: Path):
    places = _places(home)
    # As msgpack writes a string 97 long: its length reads as an "a" right before the id.
    _database(places.database, b"\xd9a" + f"{ID}/photo.png".encode(), "nothing")
    referenced = _file(places.uploads / ID / "photo.png")
    orphan = _file(places.uploads / OTHER_ID / "pasted.png")
    voice = _file(places.uploads / "audio" / OTHER_ID.replace("f", "e") / "recording.wav")
    found = orphaned(places.uploads, mentioned_ids(places.database, places.plugin_data), NOW)
    assert found == sorted([orphan, voice]) and referenced not in found


def test_a_recent_upload_or_one_lo9i_did_not_name_is_never_orphaned(home: Path):
    uploads = home / "uploads"
    _file(uploads / OTHER_ID / "draft.png", modified=NOW - 60)
    _file(uploads / "by-hand" / "notes.txt")
    assert orphaned(uploads, set(), NOW) == []


def test_a_plugin_database_mentioning_an_upload_keeps_it(home: Path):
    places = _places(home)
    _database(places.database, "nothing here")
    _database(places.plugin_data / "expenses" / "expenses.db", f"receipt at {places.uploads}/{ID}/r.pdf")
    # Not SQLite (an encrypted one): read as bytes.
    _file(places.plugin_data / "whatsapp" / "chats.db").write_bytes(b"\x00garbage" + OTHER_ID.encode() + b"\x00")
    assert {ID, OTHER_ID} <= mentioned_ids(places.database, places.plugin_data)


def test_uploads_are_left_alone_when_the_database_cant_be_read(home: Path):
    places = _places(home)
    _file(places.database).write_bytes(b"not a database at all, and long enough" * 200)
    _file(places.uploads / OTHER_ID / "pasted.png")
    report = build(places, [], [], NOW)
    assert not [i for i in report.items if i.category == "uploads"]


def test_caches_skip_what_installing_builds_browser_profiles_and_new_temporary_files(home: Path):
    plugin = home / "mcp" / "watchlist"
    pycache = _file(plugin / "src" / "watchlist" / "__pycache__" / "app.pyc").parent
    pytest_cache = _file(plugin / ".pytest_cache" / "v" / "x").parent.parent
    old_tmp = _file(plugin / "write.tmp", modified=NOW - TEMPORARY_SECONDS - 60)
    _file(plugin / "writing.tmp", modified=NOW - 60)
    _file(plugin / ".venv" / "lib" / "__pycache__" / "x.pyc")
    _file(plugin / "node_modules" / ".cache" / "x")
    profile = home / "data" / "browser" / "profile"
    _file(profile / "Local State")
    _file(profile / "Default" / ".cache" / "x")
    found = caches([home / "mcp", home / "data"], NOW)
    assert sorted(found) == sorted([pycache, pytest_cache, old_tmp])


def test_downloads_are_offered_but_cleaned_only_on_request(home: Path):
    places = _places(home)
    folder = home.parent / "Downloads"
    video = _file(folder / "A talk [aNLjh3S1IXg].mp4")
    _file(folder / "A talk [aNLjh3S1IXg].mp4.part")
    _file(folder / "taxes.pdf")
    downloads = DownloadsFolder("youtube", folder, (re.compile(r".* \[[\w-]{11}\]\.(mp4|mp3)"),))
    assert downloads.finished() == [video]
    report = build(places, downloads.finished(), [folder], NOW)
    category = next(c for c in report.categories if c.name == "downloads")
    assert category.on_request and category.freeable == _taken(video) == category.bytes
    assert report.freeable == sum(c.freeable for c in report.categories if c.name != "downloads")


def test_a_plugin_declares_where_its_downloads_go(home: Path, monkeypatch: pytest.MonkeyPatch):
    section = {"field": "YOUTUBE_DIR", "default": "{data}/videos", "files": [r".*\.mp4"]}
    assert parse("youtube", section, {"YOUTUBE_DIR": "/media/videos"}).folder == Path("/media/videos")
    assert parse("youtube", section, {"YOUTUBE_DIR": " "}).folder.parts[-2:] == ("youtube", "videos")
    with pytest.raises(ValueError):
        parse("youtube", {"field": "YOUTUBE_DIR"}, {})
    with pytest.raises(re.error):
        parse("youtube", {**section, "files": ["(unclosed"]}, {})


def test_cleaning_removes_what_was_planned_and_compacts_the_database(home: Path):
    places = _places(home)
    _database(places.database, *(b"x" * 4000 for _ in range(500)))
    with closing(sqlite3.connect(places.database)) as db:
        db.execute("DELETE FROM t")
        db.commit()
    rotated = _file(places.logs / "daemon.log.1")
    live = _file(places.logs / "daemon.log")
    orphan = _file(places.uploads / OTHER_ID / "pasted.png")
    report = build(places, [], [], NOW)
    assert {i.category for i in report.items} == {"database", "logs", "uploads"}
    done = clean(places, report.items)
    assert not done.failed and done.freed > 0
    assert not rotated.exists() and not orphan.parent.exists() and live.exists() and places.database.exists()
    assert not [i for i in build(places, [], [], NOW).items if i.category == "database"]
