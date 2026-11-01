"""Where Claude Code and Codex keep skills, for the user and in a project, and the AGENTS.md and CLAUDE.md files
next to them."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

CLAUDE = "claude"
CODEX = "codex"
# How the apps name each agent.
AGENT_NAMES = {CLAUDE: "Claude Code", CODEX: "Codex"}

# A folder of skill folders, each with a SKILL.md.
SKILLS = "skills"
# A folder of Markdown files, each a Codex custom prompt.
PROMPTS = "prompts"
# A folder of Markdown files, each a Claude Code command, in subfolders too.
COMMANDS = "commands"

# The skills an administrator gives every user of this computer.
CODEX_ADMIN_SKILLS = Path("/etc/codex/skills")


@dataclass(frozen=True)
class Place:
    agent: str
    kind: str
    folder: Path
    # The project folder it's in; None for the user's own.
    project: Path | None = None
    # The Claude Code plugin it comes with, as Claude Code names it (`name@marketplace`); "" for none.
    plugin: str = ""


def places(home: Path, projects: Sequence[Path]) -> list[Place]:
    """The user's own first, then each project's."""
    distinct = _distinct(home, projects)
    own = [
        Place(CLAUDE, SKILLS, home / ".claude" / "skills"),
        Place(CLAUDE, COMMANDS, home / ".claude" / "commands"),
        *_plugins(home, distinct),
        Place(CODEX, SKILLS, home / ".codex" / "skills"),
        Place(CODEX, SKILLS, home / ".agents" / "skills"),
        Place(CODEX, SKILLS, CODEX_ADMIN_SKILLS),
        Place(CODEX, PROMPTS, home / ".codex" / "prompts"),
    ]
    return [*own, *[p for project in distinct for p in _in_project(project)]]


def suggestions(home: Path, projects: Sequence[Path]) -> list[str]:
    """The AGENTS.md and CLAUDE.md files there are: a coding agent's instructions, never imported."""
    own = [home / ".claude" / "CLAUDE.md", home / ".codex" / "AGENTS.md"]
    names = ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md")
    found = [project / name for project in _distinct(home, projects) for name in names]
    return [str(path) for path in [*own, *found] if path.is_file()]


def _in_project(project: Path) -> list[Place]:
    return [
        Place(CLAUDE, SKILLS, project / ".claude" / "skills", project),
        Place(CLAUDE, COMMANDS, project / ".claude" / "commands", project),
        Place(CODEX, SKILLS, project / ".agents" / "skills", project),
    ]


def _plugins(home: Path, projects: list[Path]) -> list[Place]:
    """The skills and commands of the plugins Claude Code installed: the user's, and a project's when it's one of
    `projects`. Where Claude Code records them (`installed_plugins.json`), each in its own folder, its skills and
    commands where plugins keep them by default."""
    places = []
    for plugin, install in _installed_plugins(home):
        project = Path(install["projectPath"]) if install.get("projectPath") else None
        if project is not None and project not in projects:
            continue
        folder = Path(str(install["installPath"]))
        places += [Place(CLAUDE, kind, folder / kind, project, plugin) for kind in (SKILLS, COMMANDS)]
    return places


def _installed_plugins(home: Path) -> list[tuple[str, dict]]:
    """Each plugin's installs, as Claude Code lists them; none when it lists none, or nothing it can read."""
    try:
        listed = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    plugins = listed.get("plugins") if isinstance(listed, dict) else None
    if not isinstance(plugins, dict):
        return []
    return [
        (name, install)
        for name, installs in plugins.items()
        if isinstance(installs, list)
        for install in installs
        if isinstance(install, dict) and install.get("installPath")
    ]


def _distinct(home: Path, projects: Sequence[Path]) -> list[Path]:
    """Each project once, leaving out the home folder, whose skills are the user's own."""
    seen: dict[Path, None] = {}
    for project in projects:
        if project != home and project.is_dir():
            seen.setdefault(project, None)
    return list(seen)
