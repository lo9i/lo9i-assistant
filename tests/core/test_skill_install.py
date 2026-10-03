"""Installing skills from a git repository. The download is replaced by a copy of a local folder."""

import shutil
from pathlib import Path

import pytest

from assistant.core.skills import install, store

URL = "https://example.com/me/lo9i-skills.git"


@pytest.fixture
def skills_dir(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    return isolated_settings / "skills"


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """A repository with two skills under skills/, the way the download sees it."""
    root = tmp_path / "remote"
    _skill(root / "skills" / "expenses", "expenses", "Track expenses", {"scripts/add.py": "print('v1')"})
    _skill(root / "skills" / "news", "news-digest", "Daily news", {})
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]")
    (root / "skills" / "expenses" / "link.py").symlink_to("/etc/hosts")
    commits = iter(f"commit{i}" for i in range(1, 10))

    async def fetch(url: str, dest: Path) -> str:
        shutil.copytree(root, dest, symlinks=True)
        return next(commits)

    monkeypatch.setattr(install, "_fetch", fetch)
    return root


def _skill(folder: Path, name: str | None, description: str, files: dict[str, str]) -> None:
    folder.mkdir(parents=True)
    header = f"---\nname: {name}\ndescription: {description}\n---\n\n" if name else ""
    (folder / "SKILL.md").write_text(f"{header}Steps for {description}.")
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(content)


async def test_browse_lists_the_skills_a_repository_offers(skills_dir, repo):
    found = await install.browse(URL)
    assert [(f.name, f.description, f.files) for f in found] == [
        ("expenses", "Track expenses", ["scripts/add.py"]),
        ("news-digest", "Daily news", []),
    ]
    assert not skills_dir.exists()


async def test_install_copies_visible_files_and_records_the_source(skills_dir, repo):
    [skill] = await install.install(URL, ["expenses"])
    assert (skill.name, skill.files, skill.source) == ("expenses", ["scripts/add.py"], URL)
    assert not (skills_dir / "expenses" / "link.py").exists()
    assert [s.name for s in store.saved_skills()] == ["expenses"]
    assert store.installed_from("expenses") == install.Source(URL, "skills/expenses", "commit1")


async def test_update_replaces_local_changes_with_the_repository(skills_dir, repo):
    await install.install(URL, ["expenses"])
    store.save("expenses", "Mine", "My steps", {"scripts/mine.py": "x"})
    (repo / "skills" / "expenses" / "scripts" / "add.py").write_text("print('v2')")
    skill = await install.update("expenses")
    assert skill.description == "Track expenses" and skill.files == ["scripts/add.py"]
    assert (skills_dir / "expenses" / "scripts" / "add.py").read_text() == "print('v2')"
    assert store.installed_from("expenses") == install.Source(URL, "skills/expenses", "commit2")


async def test_a_skill_not_installed_from_a_repository_cant_be_updated(skills_dir, repo):
    store.save("expenses", "Mine", "My steps")
    with pytest.raises(store.SkillError, match="wasn't installed"):
        await install.update("expenses")


async def test_install_refuses_names_taken_by_other_skills(skills_dir, repo):
    store.save("expenses", "Mine", "My steps")
    with pytest.raises(store.SkillError, match="already have a skill named expenses"):
        await install.install(URL, ["expenses"])
    with pytest.raises(store.SkillError, match="no skill named missing"):
        await install.install(URL, ["missing"])
    assert store.load("expenses").description == "Mine"


async def test_a_repository_that_is_one_skill_is_named_after_the_repository(skills_dir, tmp_path, monkeypatch):
    root = tmp_path / "single"
    _skill(root, None, "Single", {"run.sh": "echo hi"})

    async def fetch(url: str, dest: Path) -> str:
        shutil.copytree(root, dest)
        return "c1"

    monkeypatch.setattr(install, "_fetch", fetch)
    [skill] = await install.install("https://example.com/me/Weather-Report.git", ["weather-report"])
    source = store.installed_from("weather-report")
    assert skill.files == ["run.sh"] and source is not None and source.path == "."


@pytest.mark.parametrize("url", ["file:///tmp/repo", "ext::sh -c touch% /tmp/x", "git@github.com:me/x.git", ""])
async def test_only_https_repositories_are_fetched(skills_dir, url):
    with pytest.raises(store.SkillError, match="https://"):
        await install.browse(url)
