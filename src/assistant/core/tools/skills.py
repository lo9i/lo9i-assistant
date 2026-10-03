"""Tools to create, run and delete skills. Saving and deleting need the user's approval: a skill
changes what the assistant does in every later conversation, so text the agent read somewhere
(a web page, an email) must not be able to plant one."""

import asyncio
import sys

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context
from assistant.core.skills import store
from assistant.core.skills.store import Skill, SkillError
from assistant.core.tools.approval import ask
from assistant.core.tools.registry import register


@register("skills")
@tool
async def save_skill(
    name: str,
    description: str,
    instructions: str,
    runtime: ToolRuntime[Context],
    files: dict[str, str] | None = None,
) -> str:
    """Create or replace a skill: reusable step-by-step instructions for a task you'll do again,
    for example a daily news digest. `name` is a short slug like news-digest; `description` is one
    line saying when to use it; `instructions` are the steps, written for yourself. `files` are
    scripts or reference files kept in the skill's folder, as {relative path: content}, for example
    {"scripts/report.py": "..."}; refer to them by that path in the instructions. Giving `files`
    replaces all of the skill's files; leaving it out keeps them. The user approves every save."""
    try:
        await asyncio.to_thread(store.check, name, files)
        existing = await _existing(name)
    except SkillError as e:
        return str(e)
    rejection = ask(_save_request(name, description, instructions, files, existing), runtime.context)
    if rejection:
        return rejection
    await asyncio.to_thread(store.save, name, description, instructions, files)
    _changed(runtime.context)
    return f"Saved skill {name}. It shows up in the skill list from the next epoch; use_skill works now."


@register("skills")
@tool
async def use_skill(name: str) -> str:
    """Load a skill's full instructions. Follow them step by step."""
    try:
        skill = await asyncio.to_thread(store.load, name)
    except SkillError as e:
        return str(e)
    return f"# Skill: {skill.name}\n\n{skill.instructions}{_files_note(skill)}"


@register("skills")
@tool
async def delete_skill(name: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a skill. The user approves it first."""
    try:
        await asyncio.to_thread(store.check, name)
        await asyncio.to_thread(store.load, name)
    except SkillError as e:
        return str(e)
    rejection = ask(
        {"tool": "delete_skill", "reason": "a deleted skill can't be restored", "command": name}, runtime.context
    )
    if rejection:
        return rejection
    await asyncio.to_thread(store.delete, name)
    _changed(runtime.context)
    return f"Deleted skill {name}."


@register("skills")
@tool
async def list_skills() -> str:
    """List the saved skills with their descriptions (current, including ones saved in this conversation)."""
    skills = await asyncio.to_thread(store.list_skills)
    return "\n".join(f"- {s.name}: {s.description}" for s in skills) or "No skills saved yet."


async def _existing(name: str) -> Skill | None:
    try:
        return await asyncio.to_thread(store.load, name)
    except SkillError:
        return None


def _save_request(
    name: str, description: str, instructions: str, files: dict[str, str] | None, existing: Skill | None
) -> dict[str, str]:
    """What the user sees before approving: the whole skill, files included."""
    action = "replaces the skill" if existing else "a new skill"
    parts = [f"{name} ({action}): {description.strip()}", instructions.strip()]
    if files is not None:
        parts += [f"--- {path} ---\n{content}" for path, content in files.items()]
    elif existing and existing.files:
        parts.append(f"Keeps its files: {', '.join(existing.files)}")
    return {
        "tool": "save_skill",
        "reason": "a skill changes what the assistant does in later conversations",
        "command": "\n\n".join(parts),
    }


def _files_note(skill: Skill) -> str:
    if not skill.files:
        return ""
    listed = "\n".join(f"- {path}" for path in skill.files)
    return (
        f"\n\n## Files\n\nThis skill's folder is {store.folder(skill.name)}; paths in the instructions are "
        f"relative to it. Run its Python scripts with {sys.executable}, through bash.\n\n{listed}"
    )


def _changed(context: Context) -> None:
    if context.bus is not None:
        context.bus.publish("skills")
