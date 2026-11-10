"""Writing an export: the data home's entries (home.TAKEN) into a gzipped tar sealed with the user's password
(sealed.py), the manifest first. Runs while the daemon does: lo9i.db and plugins' SQLite databases are taken through
SQLite's backup, each a consistent copy, never the file with its journal. Blocking: the daemon calls it in a thread."""

import logging
import os
import sqlite3
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast

from lo9i.core.i18n import said
from lo9i.core.migration import home as contents
from lo9i.core.migration.errors import MigrationError
from lo9i.core.migration.manifest import HOME, NAME, Manifest, made_here
from lo9i.core.migration.sealed import SealedWriter

logger = logging.getLogger(__name__)

_SQLITE = b"SQLite format 3\x00"
# How long a backup waits for a database another process is writing.
_BUSY_SECONDS = 10
_GZIP_LEVEL = 6


def write(home: Path, out: BinaryIO, password: str) -> Manifest:
    """Writes the export of `home` to `out`. Raises MigrationError when lo9i.db can't be copied; a plugin's database
    it can't take a copy of (another process holding it locked) is taken as it is, and logged."""
    manifest = made_here(home, [name for name in contents.TAKEN if (home / name).exists()])
    sealed = SealedWriter(out, password)
    # tarfile only writes to it. gzip's usual level: 9 takes much longer for little less, much of what's taken
    # (uploads, the browser) being compressed already.
    with tarfile.open(fileobj=cast(BinaryIO, sealed), mode="w|gz", compresslevel=_GZIP_LEVEL) as tar:
        _add_bytes(tar, NAME, manifest.to_json())
        for name in manifest.taken:
            for path in _entries(home, home / name):
                try:
                    _add(tar, home, path)
                except FileNotFoundError:
                    # Gone since it was listed (a plugin's temporary file): there's nothing to take.
                    continue
    sealed.finish()
    return manifest


def is_sqlite(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as f:
        return f.read(len(_SQLITE)) == _SQLITE


def _add(tar: tarfile.TarFile, home: Path, path: Path) -> None:
    relative = path.relative_to(home)
    arcname = f"{HOME}/{relative.as_posix()}"
    if relative.parts[0] in (contents.DATABASE, contents.PLUGIN_DATA) and is_sqlite(path):
        _add_database(tar, path, arcname, required=relative.parts[0] == contents.DATABASE)
    else:
        tar.add(path, arcname, recursive=False)


def _entries(home: Path, top: Path) -> Iterator[Path]:
    """`top` and what's in it that's taken, folders before what they hold."""
    if not _taken(home, top):
        return
    if top.is_symlink() or not top.is_dir():
        yield top
        return
    built = top == home / contents.CODE
    for folder, folders, files in os.walk(top):
        at = Path(folder)
        yield at
        names = sorted(n for n in [*folders, *files] if _taken(home, at / n, built))
        folders[:] = [n for n in folders if n in names and not (at / n).is_symlink()]
        yield from (at / n for n in names if n not in folders)


def _taken(home: Path, path: Path, built: bool = False) -> bool:
    """Files, folders, and links that lead to something inside the home by a relative path (an import refuses any
    other); never sockets or what installing a plugin builds."""
    if built and path.name in contents.BUILT:
        return False
    if path.is_symlink():
        target = os.readlink(path)
        return not os.path.isabs(target) and path.exists() and path.resolve().is_relative_to(home.resolve())
    if path.name.endswith(contents.SIDECARS) and path.parent.is_relative_to(home / contents.PLUGIN_DATA):
        return not is_sqlite(path.with_name(_without_sidecar(path.name)))
    return path.is_file() or path.is_dir()


def _without_sidecar(name: str) -> str:
    return next(name.removesuffix(s) for s in contents.SIDECARS if name.endswith(s))


def _add_database(tar: tarfile.TarFile, path: Path, arcname: str, required: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="lo9i-export-") as scratch:
        copy = Path(scratch) / path.name
        try:
            _backup(path, copy)
        except sqlite3.Error as e:
            if required:
                raise MigrationError(said("Couldn't copy {path}: {error}", path=str(path), error=str(e))) from e
            logger.warning("Couldn't take a consistent copy of %s (%s): it's taken as it is.", path, e)
            _add_as_is(tar, path, arcname)
            return
        os.chmod(copy, path.stat().st_mode & 0o777)
        tar.add(copy, arcname, recursive=False)


def _backup(path: Path, copy: Path) -> None:
    with closing(sqlite3.connect(path, timeout=_BUSY_SECONDS)) as source, closing(sqlite3.connect(copy)) as target:
        source.backup(target)


def _add_as_is(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
    tar.add(path, arcname, recursive=False)
    for sidecar in contents.SIDECARS:
        beside = path.with_name(path.name + sidecar)
        if beside.is_file():
            tar.add(beside, arcname + sidecar, recursive=False)


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    tar.addfile(info, BytesIO(data))
