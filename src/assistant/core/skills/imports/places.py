"""Where Claude Code and Codex keep skills, for the user and in a project, and the AGENTS.md and CLAUDE.md files
next to them."""

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


@dataclass(frozen=True)
class Place:
    agent: str
    kind: str
    folder: Path
    # The project folder it's in; None for the user's own.
    project: Path | None = None


def places(home: Path, projects: Sequence[Path]) -> list[Place]:
    """The user's own first, then each project's."""
    own = [
        Place(CLAUDE, SKILLS, home / ".claude" / "skills"),
        Place(CODEX, SKILLS, home / ".codex" / "skills"),
        Place(CODEX, SKILLS, home / ".agents" / "skills"),
        Place(CODEX, PROMPTS, home / ".codex" / "prompts"),
    ]
    return [*own, *[p for project in _distinct(home, projects) for p in _in_project(project)]]


def suggestions(home: Path, projects: Sequence[Path]) -> list[str]:
    """The AGENTS.md and CLAUDE.md files there are: a coding agent's instructions, never imported."""
    own = [home / ".claude" / "CLAUDE.md", home / ".codex" / "AGENTS.md"]
    names = ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md")
    found = [project / name for project in _distinct(home, projects) for name in names]
    return [str(path) for path in [*own, *found] if path.is_file()]


def _in_project(project: Path) -> list[Place]:
    return [
        Place(CLAUDE, SKILLS, project / ".claude" / "skills", project),
        Place(CODEX, SKILLS, project / ".agents" / "skills", project),
    ]


def _distinct(home: Path, projects: Sequence[Path]) -> list[Path]:
    """Each project once, leaving out the home folder, whose skills are the user's own."""
    seen: dict[Path, None] = {}
    for project in projects:
        if project != home and project.is_dir():
            seen.setdefault(project, None)
    return list(seen)
