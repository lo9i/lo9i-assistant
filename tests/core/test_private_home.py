"""lo9i's data folder and database are private from the start (core/private_home.py)."""

import os
import sqlite3
import stat

from lo9i.core import private_home
from lo9i.core.config import settings


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_a_new_home_and_database_are_only_the_users(monkeypatch, tmp_path):
    old = os.umask(0o022)
    try:
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "home" / "lo9i.db"))
        home = private_home.make_home()
        assert _mode(home) == 0o700
        database = home / "lo9i.db"
        private_home.make_database(database)
        conn = sqlite3.connect(database, isolation_level=None)
        try:
            assert conn.execute("PRAGMA journal_mode=WAL").fetchall() == [("wal",)]
            conn.execute("CREATE TABLE t (x)")
            assert _mode(database) == 0o600 and _mode(home / "lo9i.db-wal") == 0o600
        finally:
            conn.close()
    finally:
        os.umask(old)


def test_a_home_made_before_is_left_as_it_is(monkeypatch, tmp_path):
    folder = tmp_path / "home"
    folder.mkdir(mode=0o755)
    os.chmod(folder, 0o755)
    (folder / "lo9i.db").write_text("")
    os.chmod(folder / "lo9i.db", 0o644)
    monkeypatch.setattr(settings, "database_path", str(folder / "lo9i.db"))
    private_home.make_home()
    private_home.make_database(folder / "lo9i.db")
    assert _mode(folder) == 0o755 and _mode(folder / "lo9i.db") == 0o644
