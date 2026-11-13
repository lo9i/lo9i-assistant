"""How much disk a file or a folder takes, as `du` counts it: the blocks its files take, never following links, and a
file reached by several links once."""

import os
import stat
from collections.abc import Collection
from pathlib import Path


class Sizes:
    """Remembers every file it counted, so a file inside two places measured (a hard link, a category's folder inside
    another) counts in the first one only."""

    def __init__(self) -> None:
        self._seen: set[tuple[int, int]] = set()

    def of(self, path: Path, skip: Collection[Path] = ()) -> int:
        """Bytes `path` takes, a file or a whole folder, but for the folders in `skip`. 0 when it's missing."""
        try:
            found = path.lstat()
        except OSError:
            return 0
        if not stat.S_ISDIR(found.st_mode):
            return self._counted(found)
        return self._folder(path, skip)

    def _folder(self, root: Path, skip: Collection[Path]) -> int:
        total, waiting = 0, [root]
        while waiting:
            folder = waiting.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                total += self._entry(entry, waiting, skip)
        return total

    def _entry(self, entry: os.DirEntry[str], waiting: list[Path], skip: Collection[Path]) -> int:
        try:
            if entry.is_dir(follow_symlinks=False):
                if Path(entry.path) not in skip:
                    waiting.append(Path(entry.path))
                return 0
            return self._counted(entry.stat(follow_symlinks=False))
        except OSError:
            return 0

    def _counted(self, found: os.stat_result) -> int:
        key = (found.st_dev, found.st_ino)
        if key in self._seen:
            return 0
        self._seen.add(key)
        return found.st_blocks * 512
