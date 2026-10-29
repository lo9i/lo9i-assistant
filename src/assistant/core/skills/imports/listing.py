"""The skills to import, as the apps and the assistant list them: each with where it is, whether it was imported
and whether its source changed since, the name it would get here, and what may stop it working here."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from assistant.core.skills import store
from assistant.core.skills.imports import records
from assistant.core.skills.imports.found import Found, found
from assistant.core.skills.imports.names import Names
from assistant.core.skills.imports.places import AGENT_NAMES, suggestions

# Not imported yet.
NEW = "new"
# Imported, and the source is as it was then.
IMPORTED = "imported"
# Imported, and the source changed since: importing it again updates it.
CHANGED = "changed"


@dataclass(frozen=True)
class Importable:
    # Its path, which picks it (import_skills).
    id: str
    # "claude" or "codex", and how the apps name it.
    agent: str
    agent_name: str
    # "skills" for a skill, "prompts" for a Codex prompt.
    kind: str
    # The project folder it's in; "" for the user's own.
    project: str
    name: str
    description: str
    files: list[str]
    # NEW, IMPORTED or CHANGED.
    state: str
    # Its name here: the one it was imported as, or the one it would get now (another when its own is taken).
    name_here: str
    # Why it gets another name than its own; "" when it doesn't.
    renamed: str = ""
    # Why it works best handed to a coding agent: imported only when the user picks it.
    needs_agent: list[str] = field(default_factory=list)
    # Why it can't be imported.
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Importables:
    skills: list[Importable]
    # AGENTS.md and CLAUDE.md files: a coding agent's instructions, never imported. The user can ask the
    # assistant to read one and save what's useful.
    suggestions: list[str]


def listing(home: Path, projects: Sequence[Path]) -> Importables:
    imported = imported_here()
    names = Names.now({path: name for path, (name, _) in imported.items()})
    items = [_importable(item, imported.get(item.id), names) for item in found(home, projects)]
    return Importables(items, suggestions(home, projects))


def imported_here() -> dict[str, tuple[str, records.ImportRecord]]:
    """The skills imported here, by the source's path: the skill's name and its record."""
    found: dict[str, tuple[str, records.ImportRecord]] = {}
    for skill in store.saved_skills():
        record = records.read(store.folder(skill.name)) if skill.imported_from else None
        if record is not None:
            found[record.path] = (skill.name, record)
    return found


def counts(importables: Importables) -> dict[str, int]:
    """The skills not imported yet, by agent name, for asking whether to import them."""
    return dict(Counter(i.agent_name for i in importables.skills if i.state == NEW))


def _importable(item: Found, imported: tuple[str, records.ImportRecord] | None, names: Names) -> Importable:
    name_here, renamed = names.preview(item)
    return Importable(
        item.id,
        item.agent,
        AGENT_NAMES[item.agent],
        item.kind,
        item.project,
        item.name,
        item.description,
        item.files,
        _state(item, imported[1] if imported else None),
        name_here,
        renamed,
        item.needs_agent,
        item.problems,
    )


def _state(item: Found, record: records.ImportRecord | None) -> str:
    if record is None:
        return NEW
    return IMPORTED if record.digest == item.digest else CHANGED
