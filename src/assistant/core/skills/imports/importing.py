"""Copying the skills the user picked into the assistant's: the source's files (never a link to them), its
SKILL.md as the assistant reads it (`formats.py`), and the record of where it came from (`records.py`). One imported
before is updated in place; a name another skill has is handled by `names.py`."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from assistant.core.repositories import folders
from assistant.core.repositories.errors import RepositoryError
from assistant.core.skills import files as skill_files
from assistant.core.skills import store
from assistant.core.skills.errors import SkillError
from assistant.core.skills.imports import records
from assistant.core.skills.imports.found import Found, found
from assistant.core.skills.imports.listing import imported_here
from assistant.core.skills.imports.names import Names

IMPORTED = "imported"
UPDATED = "updated"
FAILED = "failed"


@dataclass(frozen=True)
class ImportOutcome:
    # The id it was picked by.
    id: str
    # IMPORTED, UPDATED or FAILED.
    action: str
    # Its name here; "" when it failed.
    name: str = ""
    # How it was named when not by its own name, or why it failed.
    note: str = ""


def import_skills(ids: Sequence[str], replace: bool, home: Path, projects: Sequence[Path]) -> list[ImportOutcome]:
    """Import the skills with these ids, in order. `replace`: a skill here with the same name is replaced
    instead of the import getting another name."""
    available = {item.id: item for item in found(home, projects)}
    imported = {path: name for path, (name, _) in imported_here().items()}
    names = Names.now(imported)
    return [_import(available.get(i), i, replace, names, i in imported) for i in dict.fromkeys(ids)]


def _import(item: Found | None, picked: str, replace: bool, names: Names, before: bool) -> ImportOutcome:
    if item is None:
        return ImportOutcome(picked, FAILED, note="It isn't among the skills to import any more: list them again.")
    if item.problems:
        return ImportOutcome(picked, FAILED, note=" ".join(item.problems))
    name, renamed = names.pick(item, replace)
    try:
        _write(item, name)
    except (SkillError, RepositoryError, OSError) as e:
        return ImportOutcome(picked, FAILED, note=str(e))
    return ImportOutcome(picked, UPDATED if before else IMPORTED, name, renamed)


def _write(item: Found, name: str) -> None:
    store.check(name)

    def fill(staging: Path) -> None:
        if item.folder is not None:
            folders.copy_files(item.folder, staging)
        text = store.text(name, item.description, item.instructions)
        (staging / skill_files.INSTRUCTIONS).write_text(text, encoding="utf-8")
        records.write(staging, records.ImportRecord(item.agent, item.id, item.digest))

    folders.build(store.folder(name), fill)
