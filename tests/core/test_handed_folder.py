"""The folder a conversation is handed to, as the web app's side panel reads it: only inside it, never what it hides
(.git, node_modules, .venv, what git ignores, links leading out), and what git says changed."""

import os
import subprocess
from pathlib import Path

import pytest

from assistant.core.handed_folder import changes, contents, deleting, diff, paths, preview, tree
from assistant.core.handed_folder.changes import FileChange, parse_status
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError, OutsideFolderError


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


async def test_a_file_is_deleted_to_the_trash_but_never_a_folder_or_what_the_tree_hides(project, trashed):
    await deleting.delete(project, "src/app.py")
    assert not (project / "src" / "app.py").exists()
    assert (trashed / "app.py").read_text() == "print('hi')\n"  # the user can take it back
    for path in ["src", "", "gone.txt"]:
        with pytest.raises(MissingPathError):
            await deleting.delete(project, path)
    for path in [".env", "node_modules/x.txt", ".git/HEAD", "../outside.txt"]:
        with pytest.raises(OutsideFolderError):
            await deleting.delete(project, path)
    assert (project / "src").is_dir() and (project / ".env").exists() and (project / ".git" / "HEAD").exists()


async def test_deleting_a_link_deletes_the_link_not_what_it_leads_to(project, trashed):
    os.symlink(project / "README.md", project / "readme-link")
    await deleting.delete(project, "readme-link")
    assert not (project / "readme-link").is_symlink()
    assert (project / "README.md").exists() and (trashed / "readme-link").is_symlink()


async def test_a_file_the_trash_cant_take_is_left_where_it_is(project, monkeypatch):
    def refused(path: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(deleting.trash, "move", refused)
    with pytest.raises(HandedFolderError, match=r"Can't move README\.md to the trash: Permission denied"):
        await deleting.delete(project, "README.md")
    assert (project / "README.md").exists()


async def test_the_tree_shows_what_git_says_was_deleted_where_it_was(project):
    (project / "src" / "app.py").unlink()
    (project / "src").rmdir()
    (project / "README.md").unlink()
    top = await tree.listed(project, "")
    assert [(e.name, e.folder, e.deleted) for e in top.entries] == [
        ("src", True, True),  # gone with everything in it
        (".gitignore", False, False),
        ("README.md", False, True),
    ]
    inside = await tree.listed(project, "src")
    assert [(e.path, e.folder, e.deleted) for e in inside.entries] == [("src/app.py", False, True)]
    with pytest.raises(MissingPathError):
        await tree.listed(project, "never-there")


async def test_a_refresh_reads_every_open_folder_and_the_changes_asking_git_once(project, monkeypatch):
    (project / "src" / "app.py").unlink()
    (project / "src").rmdir()
    (project / "docs").mkdir()
    (project / "docs" / "new.md").write_text("new")
    asked = []
    status = changes.git.status

    async def counted(root):
        asked.append(root)
        return await status(root)

    monkeypatch.setattr(changes.git, "status", counted)
    read = await tree.refreshed(project, ["", "src", "docs", "never-there", "../out", ""])
    assert len(asked) == 1
    assert [(f.path, f.contents is not None, bool(f.error)) for f in read.folders] == [
        ("", True, False),
        ("src", True, False),
        ("docs", True, False),
        ("never-there", False, True),
        ("../out", False, True),
    ]
    inside = read.folders[1].contents
    assert inside is not None and [(e.path, e.deleted) for e in inside.entries] == [("src/app.py", True)]
    assert [(c.path, c.status) for c in read.changes.changes] == [("src/app.py", "deleted"), ("docs/", "untracked")]


async def test_a_changed_file_shows_what_changed_and_a_new_or_deleted_one_whole(project):
    (project / "README.md").write_text("# Project\nMore.\n")
    modified = await diff.diff(project, "README.md")
    assert modified.status == "modified" and modified.text is not None
    assert "-# Project" not in modified.text and "+More." in modified.text and "@@" in modified.text
    (project / "new.py").write_text("x = 1\n")
    added = await diff.diff(project, "new.py")
    assert added.status == "untracked" and added.text is not None and "+x = 1" in added.text
    (project / "src" / "app.py").unlink()
    deleted = await diff.diff(project, "src/app.py")
    assert deleted.status == "deleted" and deleted.text is not None and "-print('hi')" in deleted.text


async def test_a_file_in_a_new_folder_shows_whole_but_not_one_git_ignores_there(project):
    (project / "docs").mkdir()
    (project / "docs" / "a.md").write_text("hello\n")
    (project / "docs" / ".env").write_text("SECRET=2")
    found = await diff.diff(project, "docs/a.md")
    assert found.status == "untracked" and found.text is not None and "+hello" in found.text
    with pytest.raises(OutsideFolderError):
        await diff.diff(project, "docs/.env")


async def test_only_a_file_git_lists_as_changed_has_a_diff(project):
    (project / "docs").mkdir()
    (project / "docs" / "a.md").write_text("")
    (project / ".env").write_text("SECRET=2")
    for path in ["README.md", "docs/", "docs", ".env", "../outside.txt", "node_modules/x.txt"]:
        with pytest.raises(MissingPathError):
            await diff.diff(project, path)


async def test_a_repository_with_no_commit_shows_its_files_as_new(tmp_path):
    where = tmp_path / "fresh"
    where.mkdir()
    _git(where, "init", "-q")
    (where / "a.txt").write_text("hello\n")
    _git(where, "add", "a.txt")
    found = await diff.diff(paths.root(str(where)), "a.txt")
    assert found.status == "added" and found.text is not None and "+hello" in found.text


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
