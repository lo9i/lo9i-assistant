"""Who besides the owner can reach a file or folder by its permission bits: its own bits for the group or everyone,
and a way through every folder above it. ACLs aren't read, so this is what the mode says, which is what a chmod
fixes."""

import os
import stat
from pathlib import Path
from typing import Literal

Others = Literal["group", "everyone"]
# A class's bits: read (or list) the entry itself, and pass through a folder.
_READ = {"group": stat.S_IRGRP, "everyone": stat.S_IROTH}
_PASS = {"group": stat.S_IXGRP, "everyone": stat.S_IXOTH}
_WRITE = {"group": stat.S_IWGRP, "everyone": stat.S_IWOTH}


def readers(path: Path) -> list[Others]:
    """Who besides its owner can read `path`, nearest-to-widest; [] when it's missing."""
    return [who for who in ("group", "everyone") if _reaches(path, who, _READ[who])]


def writers(path: Path) -> list[Others]:
    """Who besides its owner can write to `path` (connect to it, for a socket)."""
    return [who for who in ("group", "everyone") if _reaches(path, who, _WRITE[who])]


def mode(path: Path) -> str:
    return oct(stat.S_IMODE(path.lstat().st_mode))[2:]


def owned_by_me(path: Path) -> bool:
    return path.lstat().st_uid == os.getuid()


def _reaches(path: Path, who: Others, bit: int) -> bool:
    try:
        if not path.lstat().st_mode & bit:
            return False
        return all(folder.stat().st_mode & _PASS[who] for folder in path.absolute().parents)
    except OSError:
        return False
