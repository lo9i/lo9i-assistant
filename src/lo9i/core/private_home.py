"""lo9i's data folder and database are private from the start: the folder only its user can open (700), the database
and its write-ahead log only its user can read (600), whatever the umask. One made before stays as its user left it,
which the security audit reports (core/security_audit/local.py)."""

import os
from pathlib import Path

from lo9i.core.config import settings

_FOLDER = 0o700
_FILE = 0o600


def home() -> Path:
    """The data folder: the database's."""
    return Path(settings.database_path).expanduser().parent


def make_home() -> Path:
    """The data folder, made private when it's made here; its parents are made as usual."""
    return _private_folder(home())


def _private_folder(folder: Path) -> Path:
    if not folder.exists():
        folder.parent.mkdir(parents=True, exist_ok=True)
        folder.mkdir(mode=_FOLDER, exist_ok=True)
        os.chmod(folder, _FOLDER)  # mkdir's mode goes through the umask
    return folder


def make_database(path: Path) -> None:
    """Creates the database file private before SQLite opens it: SQLite gives its write-ahead log and shared memory
    the database's mode. A database there already is left as it is. Its folder is the data folder."""
    _private_folder(path.parent)
    if path.exists():
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE)
    os.close(descriptor)
    os.chmod(path, _FILE)  # os.open's mode goes through the umask too
