"""Moving lo9i to another computer: an export of one data home, imported into another, comes back whole but for what
each computer makes again, with the old computer's paths moved to the new one's (core/migration/)."""

import io
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lo9i.core.agent import AssistantService, HomeInUseError, WrongPasswordError
from lo9i.core.migration import applying, export, staging
from lo9i.core.migration.manifest import Manifest
from lo9i.core.repositories import platforms

PASSWORD = "correct horse battery"


def _database(path: Path, rows: list[tuple[str, str]], table: str = "store") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT)")
        db.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows)
        db.commit()


def _rows(path: Path, table: str = "store") -> dict[str, str]:
    with closing(sqlite3.connect(path)) as db:
        return dict(db.execute(f"SELECT key, value FROM {table}").fetchall())


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _old_home(user: Path) -> Path:
    """A data home in use on the old computer, with what an export takes and what it leaves."""
    home = user / ".lo9i"
    project = f"{user}/projects/site"
    _database(home / "lo9i.db", [("handoff", json.dumps({"folder": project})), ("other", "/elsewhere")])
    _database(home / "lo9i.db", [("1", project)], table="checkpoints")
    _write(home / "keys" / "secrets.key", "old key")
    _write(home / "skills" / "deploy" / "SKILL.md", f"Run {project}/deploy.sh, not {user}2/x.")
    _write(home / "mcp" / "notes" / "server.yaml", "name: notes\ncommand: '{bin}/notes'\n")
    _write(home / "mcp" / "notes" / ".source.yaml", "url: https://example.com\n")
    _write(home / "mcp" / "notes" / ".venv" / "bin" / "notes")
    _write(home / "mcp" / "notes" / "src" / "__pycache__" / "notes.pyc")
    _write(home / "data" / "notes" / "settings.json", json.dumps({"folder": f"{home}/data/notes"}))
    os.mkfifo(home / "data" / "notes" / "page.sock")
    profile = home / "data" / "browser" / "profile"
    _write(profile / "Default" / "Preferences")
    (profile / "SingletonLock").symlink_to("old-host-123")
    (profile / "Current").symlink_to("Default")
    _write(home / "uploads" / "photo.txt", f"{user}/kept as written")
    _write(home / "workspace" / "notes.md")
    _write(home / "browsers" / "chromium" / "chrome")
    _write(home / "cli_history", "hello")
    for left in ("models/e5.bin", "logs/daemon.log", "claude-workspace/a", "facts-backup-1.json", "old.db"):
        _write(home / left)
    return home


def _with_open_writer(path: Path) -> sqlite3.Connection:
    """A plugin's database with rows only in its write-ahead log, as while the plugin runs."""
    _database(path, [("a", "first")])
    db = sqlite3.connect(path)
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("INSERT INTO store VALUES ('b', ?)", (f"{path.parents[3]}/projects/site",))
    db.commit()
    return db


def _exported(home: Path, monkeypatch: pytest.MonkeyPatch) -> io.BytesIO:
    monkeypatch.setenv("HOME", str(home.parent))
    out = io.BytesIO()
    with closing(_with_open_writer(home / "data" / "notes" / "notes.db")):
        export.write(home, out, PASSWORD)
    out.seek(0)
    return out


def _new_home(user: Path) -> Path:
    """A fresh install on the new computer: a database and key of its own, and the models it downloaded."""
    home = user / ".lo9i"
    _database(home / "lo9i.db", [("fresh", "yes")])
    _write(home / "keys" / "secrets.key", "new key")
    _write(home / "models" / "e5.bin", "downloaded here")
    _write(home / "browsers" / "chromium" / "chrome", "this system's")
    return home


def test_an_export_comes_back_whole_on_the_other_computer_with_its_paths_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    old_user, new_user = tmp_path / "Users" / "me", tmp_path / "home" / "me"
    exported = _exported(_old_home(old_user), monkeypatch)
    home = _new_home(new_user)

    manifest = staging.stage(exported, PASSWORD, home, new_user)
    applied = applying.apply_staged(home)

    assert applied is not None and applied.manifest == manifest
    assert not (home / staging.STAGED).exists()
    project = f"{new_user}/projects/site"
    assert _rows(home / "lo9i.db") == {"handoff": json.dumps({"folder": project}), "other": "/elsewhere"}
    # History is never changed.
    assert _rows(home / "lo9i.db", "checkpoints") == {"1": f"{old_user}/projects/site"}
    assert _rows(home / "data" / "notes" / "notes.db") == {"a": "first", "b": project}
    assert (home / "keys" / "secrets.key").read_text() == "old key"
    assert (home / "skills" / "deploy" / "SKILL.md").read_text() == f"Run {project}/deploy.sh, not {old_user}2/x."
    assert json.loads((home / "data" / "notes" / "settings.json").read_text()) == {"folder": f"{home}/data/notes"}
    assert (home / "uploads" / "photo.txt").read_text() == f"{old_user}/kept as written"
    assert (home / "cli_history").read_text() == "hello"
    assert (home / "browsers" / "chromium" / "chrome").read_text() == "x"
    assert (home / "models" / "e5.bin").read_text() == "downloaded here"
    code = home / "mcp" / "notes"
    assert sorted(p.relative_to(code).as_posix() for p in code.rglob("*")) == [
        ".source.yaml",
        "server.yaml",
        "src",
    ]
    profile = home / "data" / "browser" / "profile"
    assert (profile / "Current").is_symlink() and not (profile / "SingletonLock").is_symlink()
    assert not (home / "data" / "notes" / "page.sock").exists()
    assert not list((home / "data" / "notes").glob("notes.db-*"))
    for left in ("logs", "claude-workspace", "facts-backup-1.json", "old.db"):
        assert not (home / left).exists()
    assert applied.set_aside is not None
    assert (applied.set_aside / "keys" / "secrets.key").read_text() == "new key"
    assert _rows(applied.set_aside / "lo9i.db") == {"fresh": "yes"}


def test_the_browsers_of_another_system_stay_behind_and_this_ones_stay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with monkeypatch.context() as elsewhere:
        elsewhere.setattr(platforms, "current", lambda: "another")
        exported = _exported(_old_home(tmp_path / "old"), monkeypatch)
    home = _new_home(tmp_path / "new")

    manifest = staging.stage(exported, PASSWORD, home, tmp_path / "new")
    applying.apply_staged(home)

    assert not manifest.same_system()
    assert (home / "browsers" / "chromium" / "chrome").read_text() == "this system's"


def test_a_wrong_password_stages_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exported = _exported(_old_home(tmp_path / "old"), monkeypatch)
    home = _new_home(tmp_path / "new")

    with pytest.raises(WrongPasswordError):
        staging.stage(exported, "not the password", home, tmp_path / "new")

    assert staging.staged(home) is None
    assert applying.apply_staged(home) is None


async def test_an_import_replaces_data_here_only_when_asked(
    service: AssistantService, isolated_settings: Path, monkeypatch: pytest.MonkeyPatch
):
    exported = _exported(_old_home(isolated_settings / "old"), monkeypatch)
    _write(isolated_settings / "uploads" / "mine.txt")

    with pytest.raises(HomeInUseError):
        await service.stage_import(exported, PASSWORD, replace=False)
    exported.seek(0)
    report = await service.stage_import(exported, PASSWORD, replace=True)

    staged = staging.staged(isolated_settings)
    assert isinstance(staged, Manifest) and report.exported_at == staged.exported_at
    assert any("Start at boot" in item for item in report.to_redo)
