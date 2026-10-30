"""The system's trash, where the folder panel puts the files the user deletes (deleting.py), so they can take one
back: the Mac's Trash, the freedesktop trash on Linux (send2trash). Tests put their own `move` in place."""

from pathlib import Path

from send2trash import send2trash


def move(path: Path) -> None:
    """Moves `path` to the trash; a link goes there itself, not what it leads to. Raises OSError when it can't (a
    volume without a trash the user may write to)."""
    send2trash(path)
