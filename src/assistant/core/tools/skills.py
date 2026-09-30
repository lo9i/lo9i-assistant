"""Tools to create, run and delete skills."""

import asyncio

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context
from assistant.core.skills import store
from assistant.core.skills.store import SkillError
from assistant.core.tools.registry import register


@register("skills")
@tool
async def save_skill(name: str, description: str, instructions: str, runtime: ToolRuntime[Context]) -> str:
    """Create or replace a skill: reusable step-by-step instructions for a task you'll do again,
    for example a daily news digest. `name` is a short slug like news-digest; `description` is one
    line saying when to use it; `instructions` are the steps, written for yourself."""
    try:
        await asyncio.to_thread(store.save, name, description, instructions)
    except SkillError as e:
        return str(e)
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
    return f"# Skill: {skill.name}\n\n{skill.instructions}"


@register("skills")
@tool
async def delete_skill(name: str, runtime: ToolRuntime[Context]) -> str:
    """Delete a skill."""
    try:
        await asyncio.to_thread(store.delete, name)
    except SkillError as e:
        return str(e)
    _changed(runtime.context)
    return f"Deleted skill {name}."


@register("skills")
@tool
async def list_skills() -> str:
    """List the saved skills with their descriptions (current, including ones saved in this conversation)."""
    skills = await asyncio.to_thread(store.list_skills)
    return "\n".join(f"- {s.name}: {s.description}" for s in skills) or "No skills saved yet."


def _changed(context: Context) -> None:
    if context.bus is not None:
        context.bus.publish("skills")
