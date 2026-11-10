"""Moving lo9i to another computer: an export of its data home (home.py says what it takes), sealed with a password
the user picks (sealed.py), and an import of it on the other computer, which is staged while the daemon runs
(staging.py) and moved into place by its next start (applying.py), the old computer's paths changed to this one's
(moved_paths.py), plugins' environments built again, and what has to be set up again said (to_redo.py).

`lo9i export` and `lo9i import` in a shell, and Settings → System in the web app, go through the daemon
(daemon/migration.py)."""

from dataclasses import dataclass, field
from pathlib import Path

from lo9i.core.i18n import said
from lo9i.core.migration.errors import HomeInUseError, MigrationError
from lo9i.core.migration.sealed import WrongPasswordError

__all__ = ["HomeInUseError", "ImportReport", "MigrationError", "WrongPasswordError", "check_password", "data_here"]

MIN_PASSWORD = 8
# What a fresh install has none of: the import replaces it only when told to.
_DATA = ("SOUL.md", "prompts", "skills", "mcp", "data", "uploads", "workspace", "arca")


@dataclass(frozen=True)
class ImportReport:
    """An import staged: where its export was made, and what has to be done again here."""

    host: str
    system: str
    exported_at: str
    to_redo: list[str] = field(default_factory=list)
    # The restart that moves it into place waits for these runs to end.
    waiting_for_runs: int = 0


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise MigrationError(said("The password needs at least {count} characters.", count=MIN_PASSWORD))


def data_here(home: Path) -> list[str]:
    """What the home holds that a fresh install doesn't (hidden files aside): its names."""
    return [name for name in _DATA if _holds(home / name)]


def _holds(path: Path) -> bool:
    if path.is_dir():
        return any(not p.name.startswith(".") for p in path.iterdir())
    return path.exists()
