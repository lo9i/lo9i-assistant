"""Moving a staged import (staging.py) into the data home, at the daemon's start, before anything there is opened:
each entry the import replaces is set aside in a folder beside the home (`<home>-before-import-<when>`), never
deleted, then the import's entries take their place. A start that stops in the middle goes on at the next one: what's
set aside is never overwritten, and only what's still staged moves in. Blocking: run in a thread."""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lo9i.core.migration import home as contents
from lo9i.core.migration.manifest import HOME, Manifest
from lo9i.core.migration.staging import STAGED, staged

logger = logging.getLogger(__name__)

# In the staged folder: where what it replaces was set aside, kept for a start that goes on after one that stopped.
_ASIDE = "set-aside"


@dataclass(frozen=True)
class Applied:
    manifest: Manifest
    # Where what the import replaced is; None when it replaced nothing.
    set_aside: Path | None


def apply_staged(home: Path) -> Applied | None:
    """Moves the staged import into place; None when none is staged."""
    manifest = staged(home)
    if manifest is None:
        return None
    folder = home / STAGED
    aside = _aside_folder(home, folder)
    for name in _replaced(home, folder / HOME, manifest):
        _set_aside(home / name, aside)
    for entry in sorted((folder / HOME).iterdir()) if (folder / HOME).is_dir() else []:
        entry.rename(home / entry.name)
    shutil.rmtree(folder)
    return Applied(manifest, aside if aside.exists() else None)


def _replaced(home: Path, brought: Path, manifest: Manifest) -> list[str]:
    """What's in the home that the import replaces: what it brings and hasn't moved in yet (with lo9i.db's journal,
    which would be applied to the new one), and what it doesn't bring, but for this system's browsers."""
    names = []
    for name in contents.TAKEN:
        in_export = name in manifest.taken and (name != contents.BROWSERS or manifest.same_system())
        if (brought / name).exists() or (not in_export and name != contents.BROWSERS):
            names.append(name)
    if (brought / contents.DATABASE).exists():
        names += [contents.DATABASE + s for s in contents.SIDECARS]
    return [n for n in names if (home / n).exists() or (home / n).is_symlink()]


def _aside_folder(home: Path, folder: Path) -> Path:
    record = folder / _ASIDE
    if record.is_file():
        return Path(record.read_text(encoding="utf-8"))
    aside = home.with_name(f"{home.name}-before-import-{datetime.now():%Y%m%d-%H%M%S}")
    record.write_text(str(aside), encoding="utf-8")
    return aside


def _set_aside(path: Path, aside: Path) -> None:
    aside.mkdir(mode=0o700, exist_ok=True)
    target = aside / path.name
    count = 1
    while target.exists() or target.is_symlink():
        target = aside / f"{path.name}.{count}"
        count += 1
    path.rename(target)
