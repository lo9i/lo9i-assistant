"""Checks a plugin repository the way lo9i reads it, so a plugin that can't be read is caught before it's
pushed: every server.yaml and SKILL.md in it, wherever it is. A server.yaml that can't be read would hide
the whole repository from Plugins and the update checker (BACKLOG A41), and a plugin outside the category
folders lo9i looks in is never listed. The extras run it before each commit:

    uv run --project <lo9i> python -m assistant.core.repositories.check <repository folder>
"""

import sys
from pathlib import Path

from assistant.core.mcp import install as servers_install
from assistant.core.repositories import categories
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.folders import SERVER_FILE, SKILL_FILE, subfolders
from assistant.core.skills import install as skills_install

# Folders that are a plugin's own environment or caches, never plugins.
_SKIPPED = {"node_modules", "__pycache__"}


def problems(root: Path) -> list[str]:
    """What's wrong with each plugin, one line each, naming its file; empty when lo9i reads them all."""
    read = {root, *subfolders(root), *categories.plugin_folders(root)}
    return [problem for folder in _plugin_folders(root) for problem in _problems(root, folder, folder in read)]


def _plugin_folders(root: Path) -> list[Path]:
    """Every folder with a server.yaml or a SKILL.md, hidden folders (.venv, .git) left out."""
    found = {path.parent for name in (SERVER_FILE, SKILL_FILE) for path in root.rglob(name)}
    return sorted(f for f in found if not _skipped(f.relative_to(root)))


def _skipped(path: Path) -> bool:
    return any(part.startswith(".") or part in _SKIPPED for part in path.parts)


def _problems(root: Path, folder: Path, read: bool) -> list[str]:
    where = folder.relative_to(root).as_posix() or "."
    if not read:
        known = ", ".join(categories.CATEGORIES)
        return [f"{where}: lo9i doesn't look in this folder; put it in a category folder ({known})."]
    if (folder / SERVER_FILE).is_file():
        return _server_problems(root, folder)
    skill = skills_install.read(root, folder)
    if skill is None:
        return [f"{where}/{SKILL_FILE}: lo9i can't read it as a skill: its name isn't one a skill can have."]
    return [f"{where}/{SKILL_FILE}: {problem}" for problem in skill.skill.problems]


def _server_problems(root: Path, folder: Path) -> list[str]:
    """A server's skill is read with it: one with problems makes the server unreadable too."""
    try:
        servers_install.read(root, folder)
    except RepositoryError as e:
        return [str(e)]
    return []


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    found = problems(root)
    for problem in found:
        print(problem, file=sys.stderr)
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
