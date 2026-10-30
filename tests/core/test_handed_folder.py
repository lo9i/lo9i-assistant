"""The folder a conversation is handed to, as the web app's side panel reads it: only inside it, never what it hides
(.git, node_modules, .venv, what git ignores, links leading out), and what git says changed."""

import os
import subprocess
from pathlib import Path

import pytest

from assistant.core.handed_folder import changes, contents, paths, preview
from assistant.core.handed_folder.changes import FileChange, parse_status
from assistant.core.handed_folder.paths import MissingPathError, OutsideFolderError


@pytest.fixture(autouse=True)
def _plain_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Git without the user's config, so their global ignore file doesn't change what the tests see."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=where, check=True, capture_output=True
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A repository with a commit, an ignored build folder and a .env, node_modules and a .venv."""
    where = tmp_path / "project"
    (where / "src").mkdir(parents=True)
    (where / "src" / "app.py").write_text("print('hi')\n")
    (where / "README.md").write_text("# Project\n")
    (where / ".gitignore").write_text("build/\n.env\n*.log\n")
    _git(where, "init", "-q")
    _git(where, "add", ".")
    _git(where, "commit", "-qm", "start")
    for hidden in ["build", "node_modules", ".venv"]:
        (where / hidden).mkdir()
        (where / hidden / "x.txt").write_text("x")
    (where / ".env").write_text("SECRET=1")
    (where / "debug.log").write_text("log")
    return paths.root(str(where))


def _names(listing: contents.FolderContents) -> list[str]:
    return [e.name for e in listing.entries]


async def test_a_folder_lists_folders_first_without_what_git_ignores_or_is_always_hidden(project):
    listing = await contents.contents(project, "")
    assert _names(listing) == ["src", ".gitignore", "README.md"]
    assert [(e.path, e.folder) for e in (await contents.contents(project, "src/")).entries] == [("src/app.py", False)]


async def test_outside_a_repository_only_the_always_hidden_folders_are_left_out(tmp_path):
    where = tmp_path / "plain"
    (where / "node_modules").mkdir(parents=True)
    (where / "a.log").write_text("x")
    assert _names(await contents.contents(paths.root(str(where)), "")) == ["a.log"]


@pytest.mark.parametrize("path", ["..", "../outside.txt", "src/../../outside.txt", "/etc/passwd", "a\0b"])
async def test_paths_that_reach_outside_the_folder_are_refused(project, path):
    (project.parent / "outside.txt").write_text("no")
    with pytest.raises(OutsideFolderError):
        await preview.preview(project, path)
    with pytest.raises(OutsideFolderError):
        await contents.contents(project, path)


async def test_a_link_leading_outside_is_left_out_and_refused(project):
    (project.parent / "outside.txt").write_text("no")
    os.symlink(project.parent / "outside.txt", project / "out.txt")
    os.symlink(project.parent, project / "up")
    assert "out.txt" not in _names(await contents.contents(project, ""))
    for path in ["out.txt", "up/outside.txt"]:
        with pytest.raises(OutsideFolderError):
            await preview.preview(project, path)


async def test_hidden_or_ignored_paths_and_links_to_them_are_refused(project):
    os.symlink(project / ".env", project / "settings.txt")
    for path in [".env", "build/x.txt", "node_modules/x.txt", ".git/config", "settings.txt"]:
        with pytest.raises(OutsideFolderError):
            await preview.preview(project, path)
    with pytest.raises(OutsideFolderError):
        await contents.contents(project, "build")


async def test_a_file_is_previewed_as_text_its_start_when_big_and_none_when_binary(project):
    assert (await preview.preview(project, "src/app.py")).text == "print('hi')\n"
    (project / "image.bin").write_bytes(b"\x89PNG\0\0data")
    binary = await preview.preview(project, "image.bin")
    assert binary.text is None and binary.size == 10
    (project / "big.txt").write_text("é" * preview.MAX_BYTES)
    big = await preview.preview(project, "big.txt")
    assert big.truncated and big.text is not None and set(big.text) == {"é"}
    with pytest.raises(MissingPathError):
        await preview.preview(project, "src")
    with pytest.raises(MissingPathError):
        await preview.preview(project, "gone.txt")


async def test_changes_are_what_git_status_says_under_the_folder(project):
    (project / "README.md").write_text("changed\n")
    (project / "src" / "app.py").unlink()
    (project / "new.py").write_text("")
    (project / "docs").mkdir()
    (project / "docs" / "a.md").write_text("")
    (project / "staged.py").write_text("")
    _git(project, "add", "staged.py")
    found = await changes.changes(project)
    assert found.repository and sorted((c.path, c.status) for c in found.changes) == [
        ("README.md", "modified"),
        ("docs/", "untracked"),
        ("new.py", "untracked"),
        ("src/app.py", "deleted"),
        ("staged.py", "added"),
    ]
    below = await changes.changes(project / "src")
    assert [(c.path, c.status) for c in below.changes] == [("app.py", "deleted")]


async def test_a_folder_outside_a_repository_has_no_changes(tmp_path):
    assert await changes.changes(tmp_path) == changes.FolderChanges(repository=False, changes=[])


def test_status_is_read_with_renames_conflicts_and_the_folders_place_in_the_repository():
    out = b"R  app/new.py\0app/old.py\0UU app/both.py\0 M other/x.py\0?? app/tmp/\0AM app/added.py\0"
    assert parse_status(out, "app/") == [
        FileChange("old.py", "deleted"),
        FileChange("new.py", "added"),
        FileChange("both.py", "modified"),
        FileChange("tmp/", "untracked"),
        FileChange("added.py", "added"),
    ]
