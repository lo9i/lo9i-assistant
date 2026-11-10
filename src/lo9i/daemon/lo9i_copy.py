"""A copy of the lo9i this daemon runs, to install on another computer it's moving to (daemon/moves.py): its files as
scripts/deploy.sh copies them, without what's this computer's (the repository, its environment, .env, caches, the
web app's packages, worktrees), the web app built, and the commit it comes from in .lo9i-version, which the copy's
Settings show as its version. Blocking: run in a thread."""

import json
import os
import tarfile
from collections.abc import Iterator
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from lo9i.daemon.updates import VERSION_FILE
from lo9i.protocol import Commit

# Left out at the top of the checkout, and wherever they are.
_TOP = frozenset({".git", ".venv", ".env", "workspace", ".idea", ".claude", VERSION_FILE})
_ANYWHERE = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules", ".svelte-kit"})


def write(root: Path, out: Path, commit: Commit | None) -> None:
    with tarfile.open(out, "w:gz") as tar:
        for path in _files(root):
            tar.add(path, path.relative_to(root).as_posix(), recursive=False)
        if commit is not None:
            data = (json.dumps(asdict(commit)) + "\n").encode()
            info = tarfile.TarInfo(VERSION_FILE)
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, BytesIO(data))


def _files(root: Path) -> Iterator[Path]:
    for folder, folders, files in os.walk(root):
        at = Path(folder)
        left_out = _TOP | _ANYWHERE if at == root else _ANYWHERE
        kept = sorted(n for n in folders if n not in left_out)
        # Links to folders aren't walked into: they're taken as links.
        folders[:] = [n for n in kept if not (at / n).is_symlink()]
        if at != root:
            yield at
        yield from (at / n for n in kept if (at / n).is_symlink())
        yield from (at / n for n in sorted(files) if n not in left_out and not (at / n).is_socket())
