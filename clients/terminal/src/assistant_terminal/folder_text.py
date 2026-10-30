"""How /folder writes the folder panel's folder (core/handed_folder/): each file or folder with what git says changed
there, as git's short status does (M, A, D, U; a dot beside a folder with changes inside), what was deleted struck
through where it was, and the changed list."""

from pathlib import PurePosixPath

from rich.text import Text

from assistant.core.agent import FileChange, FolderEntry
from assistant_terminal.i18n import translatable

_LETTERS = {"modified": "M", "added": "A", "deleted": "D", "untracked": "U"}
_STYLES = {"modified": "yellow", "added": "green", "deleted": "red", "untracked": "green", "inside": "yellow"}
INSIDE = "inside"

# The panel's two ways of showing a file git says changed.
CHANGES = translatable("Changes")
WHOLE_FILE = translatable("Whole file")


class ChangeMarks:
    """What the tree marks beside each file and folder, from what git says changed."""

    def __init__(self, changes: list[FileChange]) -> None:
        self._files = {c.path: c.status for c in changes if not c.path.endswith("/")}
        # Git lists a folder nothing in is tracked once, as "docs/", for everything inside it.
        self._untracked = [c.path for c in changes if c.path.endswith("/")]
        self._holding = {folder for c in changes for folder in _parents(c.path)}

    def of(self, path: str, folder: bool) -> str | None:
        """A change's kind, INSIDE for a folder with changes in it, None when nothing changed there."""
        if any(f"{path}/".startswith(prefix) for prefix in self._untracked):
            return "untracked"
        if folder:
            return INSIDE if path in self._holding else None
        return self._files.get(path)

    def file_change(self, path: str) -> str | None:
        """What git says changed in the file at `path`; None when it doesn't list it."""
        mark = self.of(path, folder=False)
        return None if mark == INSIDE else mark


def entry_label(entry: FolderEntry, mark: str | None) -> Text:
    """The entry's name, a folder's with a slash, struck through when it was deleted, then its mark."""
    label = Text(entry.name + ("/" if entry.folder else ""), style="strike dim" if entry.deleted else "")
    if mark is not None:
        label.append(f" {_LETTERS.get(mark, '•')}", style=f"bold {_STYLES[mark]}")
    return label


def change_label(change: FileChange) -> Text:
    """A line of the changed list: its mark, then its path, struck through when it was deleted."""
    label = Text(f"{_LETTERS[change.status]} ", style=f"bold {_STYLES[change.status]}")
    label.append(change.path, style="strike dim" if change.status == "deleted" else "")
    return label


def _parents(path: str) -> list[str]:
    """The folders `path` is in, outermost first: "a/b/c.txt" is in "a" and "a/b"."""
    parts = PurePosixPath(path.rstrip("/")).parts[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]
