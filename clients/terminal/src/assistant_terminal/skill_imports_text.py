"""How Claude Code's and Codex's skills to import read, in /import-skills (the screen and the plain REPL): where each
comes from, whether it was imported or changed since, what may stop it working here, and how its import went."""

import re

from assistant.core.agent import Importable, ImportOutcome
from assistant_terminal.i18n import t


def selectable(item: Importable) -> bool:
    """Imported and unchanged, or broken: nothing to import."""
    return item.state != "imported" and not item.problems


def label(item: Importable) -> str:
    plugin = item.plugin.split("@")[0]
    project = item.project.rstrip("/").rsplit("/", 1)[-1]
    where = " · ".join(part for part in (item.agent_name, plugin, project) if part)
    state = {
        "imported": " · " + t("imported as {name}", name=item.name_here),
        "changed": " · " + t("changed since imported"),
    }.get(item.state, "")
    flags = " · " + t("for a coding agent") if item.needs_agent else ""
    return f"{item.name} ({where}){state}{flags}{' · ' + t('has problems') if item.problems else ''}"


def detail(item: Importable | None) -> str:
    if item is None:
        return t("Claude Code and Codex have no skills on this computer.")
    lines = [item.description, item.id]
    if item.state == "new" and item.renamed:
        lines.append(t("Will be {renamed}.", renamed=item.renamed))
    if item.needs_agent:
        lines.append(t("Works best handed to a coding agent: {reasons}", reasons=" ".join(item.needs_agent)))
    lines += item.problems
    return "\n".join(lines)


def suggestions(files: list[str]) -> str:
    if not files:
        return ""
    return t(
        "Not imported, a coding agent's instructions (ask the assistant to read one): {files}", files=", ".join(files)
    )


def outcome(done: ImportOutcome) -> str:
    name = done.id.rstrip("/").rsplit("/", 1)[-1]
    if done.action == "failed":
        return f"{name}: {done.note}"
    action = t("updated") if done.action == "updated" else t("imported")
    said = t("{source}: {action} as {name}", source=name, action=action, name=done.name)
    return f"{said} ({done.note})" if done.note else said


def numbers(text: str, most: int) -> list[int]:
    """The numbers picked, like `1 3 5-7`, from 1 to `most`, in order."""
    chosen: set[int] = set()
    for first, last in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", text):
        chosen.update(range(int(first), min(int(last or first), most) + 1))
    return sorted(n for n in chosen if 1 <= n <= most)
