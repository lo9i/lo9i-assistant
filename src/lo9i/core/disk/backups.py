"""Copies of lo9i's data that older versions left in the data home before changing it (`lo9i-before-accounts.db`,
`facts-backup-2026-10-25.json`), and the folders an import set aside beside it (`.lo9i-before-import-<when>`,
core/migration/applying.py). Only the first are cleaned: an import's folder holds the whole of the data it replaced."""

from pathlib import Path

from lo9i.core.disk.places import SIDECARS

_DATABASE_COPIES = "lo9i-before-*.db"
_FACT_COPIES = "facts-backup-*.json"


def old_copies(home: Path, live: Path) -> list[Path]:
    """The copies in `home`, with what SQLite kept beside them; never `live`, the database lo9i uses, or its files."""
    databases = sorted(home.glob(_DATABASE_COPIES))
    found = [
        *databases,
        *(p.with_name(p.name + s) for p in databases for s in SIDECARS),
        *sorted(home.glob(_FACT_COPIES)),
    ]
    kept = {live, *(live.with_name(live.name + s) for s in SIDECARS)}
    return [p for p in found if p.is_file() and not p.is_symlink() and p not in kept]


def set_aside(home: Path) -> list[Path]:
    """The folders imports set aside beside `home`."""
    return sorted(p for p in home.parent.glob(f"{home.name}-before-import-*") if p.is_dir() and not p.is_symlink())
