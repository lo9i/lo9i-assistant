"""The skills and prompts in each place (`places.py`), read as the assistant's (`formats.py`), with a digest of
their files to tell later whether the source changed."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from assistant.core.i18n import said
from assistant.core.repositories.folders import MAX_BYTES, MAX_FILES, files_in
from assistant.core.skills import files as skill_files
from assistant.core.skills import store
from assistant.core.skills.imports import formats
from assistant.core.skills.imports.places import AGENT_NAMES, PROMPTS, Place, places


@dataclass(frozen=True)
class Found:
    # Its path: the skill's folder, or a prompt's file. Stable, so it names it when it's picked.
    id: str
    agent: str
    # places.SKILLS or places.PROMPTS.
    kind: str
    # The project folder it's in; "" for the user's own.
    project: str
    # The name it has here: its own, made a valid skill name.
    name: str
    description: str
    # As the assistant reads them (formats.py).
    instructions: str
    # Next to its SKILL.md, relative to its folder; none for a prompt.
    files: list[str]
    digest: str
    # Why it works best handed to a coding agent (formats.needs_agent).
    needs_agent: list[str]
    # Why it can't be imported.
    problems: list[str]
    # Where its files are; None for a prompt.
    folder: Path | None


def found(home: Path, projects: Sequence[Path]) -> list[Found]:
    return [item for place in places(home, projects) for item in _in(place)]


def _in(place: Place) -> list[Found]:
    if not place.folder.is_dir():
        return []
    if place.kind == PROMPTS:
        return [_prompt(place, f) for f in sorted(place.folder.glob("*.md")) if f.is_file()]
    # Linked skill folders count, as both agents follow them; hidden ones are the agent's own (Codex's .system).
    folders = sorted(p for p in place.folder.iterdir() if p.is_dir() and not p.name.startswith("."))
    return [item for f in folders if (item := _skill(place, f)) is not None]


def _skill(place: Place, folder: Path) -> Found | None:
    path = folder / skill_files.INSTRUCTIONS
    if not path.is_file():
        return None
    agent_name = AGENT_NAMES[place.agent]
    meta, body, header_problems = store.parse(_read(path))
    skill_name = formats.name(str(meta.get("name") or folder.name))
    instructions = formats.skill_instructions(body, agent_name)
    files = skill_files.listed(folder)
    paths = files_in(folder)
    # A folder too big to import isn't read whole for its digest.
    too_big = _size(paths)
    return Found(
        str(folder),
        place.agent,
        place.kind,
        _project(place),
        skill_name,
        formats.description(meta, body),
        instructions,
        files,
        "" if too_big else _digest(folder, paths),
        [*formats.needs_agent(meta, body, agent_name), *_openai_dependencies(folder)],
        [*header_problems, *formats.problems(skill_name, instructions, files), *too_big],
        folder,
    )


def _prompt(place: Place, file: Path) -> Found:
    meta, body, header_problems = store.parse(_read(file))
    prompt_name = formats.name(file.stem)
    instructions = formats.prompt_instructions(body, meta)
    return Found(
        str(file),
        place.agent,
        place.kind,
        _project(place),
        prompt_name,
        formats.description(meta, body),
        instructions,
        [],
        _digest(file.parent, [file]),
        formats.needs_agent(meta, body, AGENT_NAMES[place.agent]),
        [*header_problems, *formats.problems(prompt_name, instructions, [])],
        None,
    )


def _openai_dependencies(folder: Path) -> list[str]:
    """Codex skills declare the tools they connect to (MCP servers) in agents/openai.yaml."""
    declared = folder / "agents" / "openai.yaml"
    if declared.is_file() and "dependencies:" in _read(declared):
        return [said("It needs tools Codex connects to (dependencies in agents/openai.yaml).")]
    return []


def _size(paths: list[Path]) -> list[str]:
    if len(paths) > MAX_FILES or sum(p.stat().st_size for p in paths) > MAX_BYTES:
        return [
            said("It has more than {files} files or {megabytes} MB.", files=MAX_FILES, megabytes=MAX_BYTES // 1_000_000)
        ]
    return []


def _digest(root: Path, paths: list[Path]) -> str:
    """Of its files' paths and contents, so a change to any of them, or a file added or removed, shows."""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _project(place: Place) -> str:
    return str(place.project) if place.project else ""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
