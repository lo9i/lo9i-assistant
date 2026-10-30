"""What changed in a file of the handed folder, as git shows it (`git diff` against the last commit), for the
panel to show a changed file's changes rather than its text. Only a file git lists as changed (changes.py), so what
the tree hides never shows here either; a new file shows whole, as added, and a deleted one as what it had."""

from dataclasses import dataclass
from pathlib import Path

from assistant.core.handed_folder import changes, git, paths, preview
from assistant.core.handed_folder.changes import ChangeKind, FileChange
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError

# No colour, and git's own diff whatever the user set up: an external diff tool would open a window.
_DIFF = ("diff", "--no-color", "--no-ext-diff")


@dataclass(frozen=True)
class FileDiff:
    # Relative to the handed folder.
    path: str
    status: ChangeKind
    # The unified diff; None when it isn't text git can show.
    text: str | None
    # Bigger than preview.MAX_BYTES: `text` is its start.
    truncated: bool


async def diff(root: Path, path: str) -> FileDiff:
    """Raises MissingPathError for a path git doesn't list as a changed file (an untracked folder itself included),
    OutsideFolderError for one in an untracked folder the tree doesn't show, HandedFolderError when git can't show
    it."""
    where = paths.normal(path)
    change = await _change(root, where)
    out = await _git_diff(root, change)
    if out is None:
        raise HandedFolderError(f"git can't show what changed in {where}.")
    truncated = len(out) > preview.MAX_BYTES
    text = preview.as_text(out[: preview.MAX_BYTES], whole=not truncated)
    return FileDiff(where, change.status, text, truncated)


async def _change(root: Path, where: str) -> FileChange:
    """The file's change: as git lists it, or untracked inside a folder git lists once as untracked, when the tree
    shows it there (git lists the folder, not an ignored file in it)."""
    found = (await changes.changes(root)).changes
    change = next((c for c in found if c.path == where and not c.path.endswith("/")), None)
    if change is None and await _in_new_folder(root, where, found):
        change = FileChange(where, "untracked")
    if change is None:
        raise MissingPathError(f"{where or '.'} has no changes to show.")
    return change


async def _in_new_folder(root: Path, where: str, found: list[FileChange]) -> bool:
    if not where or not any(c.path.endswith("/") and where.startswith(c.path) for c in found):
        return False
    return (await paths.shown(root, where)).is_file()


async def _git_diff(root: Path, change: FileChange) -> bytes | None:
    """Against the last commit, staged changes and not; a file git doesn't track yet, or one in a repository with no
    commit, as all new."""
    if change.status != "untracked":
        out = await git.run(root, *_DIFF, "HEAD", "--", change.path)
        if out is not None:
            return out
    return await git.run(root, *_DIFF, "--no-index", "--", "/dev/null", change.path, found=(0, 1))
