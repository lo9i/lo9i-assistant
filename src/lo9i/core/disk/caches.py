"""What tools leave in plugins' folders that they make again when it's missing: Python's bytecode, test and linter
caches, package managers' caches, temporary files. Never inside what installing builds (.venv, node_modules,
core/migration/home.py::BUILT), which the plugin runs from."""

import os
from collections.abc import Iterable
from pathlib import Path

CACHE_FOLDERS = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache", ".npm", ".uv-cache", ".pip-cache"}
)
_TEMPORARY = (".tmp", ".temp")
# A temporary file younger than this may be one a plugin is writing, to rename into place when it's done.
TEMPORARY_SECONDS = 24 * 3600
_NOT_ENTERED = frozenset({".venv", "node_modules", ".git"})
# A browser's profile (the browser plugin's, with its sign-ins) is left whole: Chromium writes this file at its top.
_BROWSER_PROFILE = "Local State"


def caches(roots: Iterable[Path], now: float) -> list[Path]:
    """The cache folders and old temporary files under each of `roots`."""
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found += _under(root, now)
    return found


def _under(root: Path, now: float) -> list[Path]:
    found: list[Path] = []
    for folder, names, files in os.walk(root):
        here = Path(folder)
        if _BROWSER_PROFILE in files:
            names.clear()
            continue
        found += [here / name for name in names if name in CACHE_FOLDERS and not (here / name).is_symlink()]
        found += [here / name for name in files if name.endswith(_TEMPORARY) and _old(here / name, now)]
        names[:] = [name for name in names if name not in CACHE_FOLDERS and name not in _NOT_ENTERED]
    return found


def _old(path: Path, now: float) -> bool:
    try:
        return not path.is_symlink() and now - path.stat().st_mtime > TEMPORARY_SECONDS
    except OSError:
        return False
