"""An import, made ready while the daemon runs: the export opened with its password and unpacked into the data home's
`STAGED` folder, the old computer's paths there changed to this one's. The daemon moves it into place when it starts
next (applying.py), before it opens anything there. Blocking: run in a thread."""

import shutil
import sys
import tarfile
import zlib
from pathlib import Path
from typing import BinaryIO, cast

from lo9i.core.i18n import said
from lo9i.core.migration import home as contents
from lo9i.core.migration import moved_paths
from lo9i.core.migration.errors import MigrationError
from lo9i.core.migration.manifest import HOME, NAME, Manifest
from lo9i.core.migration.moved_paths import Moved
from lo9i.core.migration.sealed import SealedReader
from lo9i.core.uv import find as find_uv

# In the data home: the import the next start moves into place, and the one being unpacked.
STAGED = ".import"
_UNPACKING = ".import-unpacking"


def stage(source: BinaryIO, password: str, home: Path, user_home: Path) -> Manifest:
    """Unpacks the export in `source` for the next start, in place of one staged before. `user_home`: this computer's
    home folder, the old one's paths are moved to. Raises MigrationError (WrongPasswordError for a wrong password)."""
    scratch = home / _UNPACKING
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        manifest = _unpack(SealedReader(source, password), scratch)
        moved_paths.rewrite(scratch / HOME, Moved(moved(manifest, home, user_home)))
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    shutil.rmtree(home / STAGED, ignore_errors=True)
    scratch.rename(home / STAGED)
    return manifest


def staged(home: Path) -> Manifest | None:
    """The import waiting for the next start, if one is."""
    manifest = home / STAGED / NAME
    return Manifest.from_json(manifest.read_bytes()) if manifest.is_file() else None


def moved(manifest: Manifest, home: Path, user_home: Path) -> list[tuple[str, str]]:
    """Each path of the old computer with this one's, from the most specific."""
    pairs = [
        (manifest.python, sys.executable),
        (manifest.uv, find_uv() or ""),
        (manifest.data_home, str(home)),
        (manifest.user_home, str(user_home)),
    ]
    return [(old, new) for old, new in pairs if old and new and old != new]


def _unpack(reader: SealedReader, scratch: Path) -> Manifest:
    try:
        # tarfile only reads from it.
        with tarfile.open(fileobj=cast(BinaryIO, reader), mode="r|gz") as tar:
            manifest = _manifest(tar)
            scratch.mkdir(mode=0o700)
            (scratch / NAME).write_bytes(manifest.to_json())
            for member in tar:
                if _wanted(member, manifest):
                    tar.extract(member, scratch, filter="data")
    except (tarfile.TarError, zlib.error, EOFError) as e:
        raise MigrationError(said("The export is damaged: {error}", error=str(e))) from e
    return manifest


def _manifest(tar: tarfile.TarFile) -> Manifest:
    first = tar.next()
    read = tar.extractfile(first) if first is not None and first.name == NAME else None
    if read is None:
        raise MigrationError(said("This file isn't a lo9i export."))
    return Manifest.from_json(read.read())


def _wanted(member: tarfile.TarInfo, manifest: Manifest) -> bool:
    """What's under the home, but the browsers downloaded for another system."""
    parts = Path(member.name).parts
    if len(parts) < 2 or parts[0] != HOME or parts[1] not in contents.TAKEN:
        return False
    return parts[1] != contents.BROWSERS or manifest.same_system()
