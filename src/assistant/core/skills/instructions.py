"""A skill as the assistant reads it: its problems, its instructions, then its files. use_skill returns it,
and the system prompt holds it for a skill pinned to the conversation (core/conversation/pinned.py)."""

import sys

from assistant.core.skills import store
from assistant.core.skills.store import Skill


def render(skill: Skill) -> str:
    return f"{_problems_note(skill)}{skill.instructions}{_files_note(skill)}"


def _problems_note(skill: Skill) -> str:
    if not skill.problems:
        return ""
    found = "\n".join(f"- {problem}" for problem in skill.problems)
    return f"This skill has problems; tell the user if they stop you from following it:\n{found}\n\n"


def _files_note(skill: Skill) -> str:
    if not skill.files:
        return ""
    listed = "\n".join(f"- {path}" for path in skill.files)
    return (
        f"\n\n## Files\n\nThis skill's folder is {store.folder(skill.name)}; paths in the instructions are "
        f"relative to it. Run its Python scripts with {sys.executable}, through bash.\n\n{listed}"
    )
