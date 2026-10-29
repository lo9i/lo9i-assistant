"""Tools to import skills from other coding agents on this computer (Claude Code, Codex; core/skills/imports/).
Listing reads only; importing needs the user's approval of the list, as saving a skill does: a skill changes what
the assistant does in every later conversation, and its scripts run here."""

import asyncio
from pathlib import Path

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_store
from assistant.core.skills.imports import importing, listing, projects
from assistant.core.skills.imports.listing import Importable, Importables
from assistant.core.tools.approval import ask
from assistant.core.tools.registry import register


@register("skills", group="skill-writing")
@tool
async def list_importable_skills(runtime: ToolRuntime[Context]) -> str:
    """List the skills Claude Code and Codex have on this computer that can be copied into yours: whether each was
    imported, or changed since. Show the list for the user to pick from; import only what they pick."""
    found = await _listing(runtime)
    return _listed(found) or "Claude Code and Codex have no skills on this computer."


@register("skills", group="skill-writing")
@tool
async def import_skills(ids: list[str], runtime: ToolRuntime[Context], replace: bool = False) -> str:
    """Copy the skills the user picked from list_importable_skills, by id. One imported before is updated from its
    source. A name you already have gets the agent's added (pdf-claude) unless `replace`. The user approves it."""
    found = {i.id: i for i in (await _listing(runtime)).skills}
    picked = [found[i] for i in ids if i in found]
    if not picked:
        return "None of these ids is among the skills to import: list them again."
    rejection = ask(_request(picked, replace), runtime.context)
    if rejection:
        return rejection
    known = await projects.known(require_store(runtime.store), runtime.context.user_id)
    outcomes = await asyncio.to_thread(importing.import_skills, ids, replace, Path.home(), known)
    if runtime.context.bus is not None and any(o.action != importing.FAILED for o in outcomes):
        runtime.context.bus.publish("skills")
    return "\n".join(f"- {o.id}: {o.action} {o.name}{f' ({o.note})' if o.note else ''}".rstrip() for o in outcomes)


async def _listing(runtime: ToolRuntime[Context]) -> Importables:
    known = await projects.known(require_store(runtime.store), runtime.context.user_id)
    return await asyncio.to_thread(listing.listing, Path.home(), known)


def _listed(found: Importables) -> str:
    lines = [_line(i) for i in found.skills]
    if found.suggestions:
        lines.append(
            "Not imported, a coding agent's instructions (offer to read one and save what's useful as a skill): "
            + ", ".join(found.suggestions)
        )
    return "\n".join(lines)


def _line(item: Importable) -> str:
    where = f"{item.agent_name}, project {item.project}" if item.project else item.agent_name
    notes = [_state(item)]
    if item.renamed:
        notes.append(item.renamed)
    if item.needs_agent:
        notes.append(f"works best handed to a coding agent: {' '.join(item.needs_agent)}")
    if item.problems:
        notes.append(f"can't be imported: {' '.join(item.problems)}")
    return f"- id {item.id}: {item.name} ({where}): {item.description} [{'; '.join(notes)}]"


def _state(item: Importable) -> str:
    if item.state == listing.IMPORTED:
        return f"imported as {item.name_here}"
    if item.state == listing.CHANGED:
        return f"changed since imported as {item.name_here}: importing it again updates it"
    return "new"


def _request(picked: list[Importable], replace: bool) -> dict[str, str]:
    """What the user sees before approving: each skill, where it comes from and the name it gets."""
    if replace:
        lines = [f"{i.name} ← {i.id}" for i in picked]
        lines.append("A skill of yours with the same name is replaced; a built-in or a plugin's never is.")
    else:
        lines = [f"{i.name_here} ← {i.id}{f' ({i.renamed})' if i.renamed else ''}" for i in picked]
    return {
        "tool": "import_skills",
        "reason": "imported skills change what the assistant does, and their scripts run here",
        "command": "\n".join(lines),
    }
