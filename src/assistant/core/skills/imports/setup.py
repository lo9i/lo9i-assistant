"""Asked once, when the assistant is installed (install.sh): import the skills Claude Code and Codex have on this
computer? All of them, some picked from a list, or none. Nothing is asked when there's none to import, or after it
was answered. "All" leaves out those that work best handed to a coding agent: they're imported only when picked.

Runs in the terminal install.sh runs in, before the daemon starts: skills are files, so it needs no daemon. Only the
user's own skills are offered here; projects' come with /import-skills, once the assistant knows them."""

import re
from collections.abc import Callable
from pathlib import Path

from assistant.core.config import settings
from assistant.core.skills.imports import importing, listing
from assistant.core.skills.imports.listing import Importable

# In the skills folder, hidden like an install in progress, so it's never read as a skill.
_ASKED = ".imports-asked"


def main(ask: Callable[[str], str] = input, home: Path | None = None) -> None:
    marker = Path(settings.skills_dir).expanduser() / _ASKED
    if marker.exists():
        return
    new = [i for i in listing.listing(home or Path.home(), []).skills if i.state == listing.NEW and not i.problems]
    if not new:
        return
    try:
        picked = _picked(new, ask)
    except EOFError:
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    if picked:
        _report(importing.import_skills([i.id for i in picked], False, home or Path.home(), []))


def _picked(new: list[Importable], ask: Callable[[str], str]) -> list[Importable]:
    print(_found(new))
    answer = ask("Import them into the assistant's skills? [a]ll, [p]ick, [s]kip (s): ").strip().lower()
    if answer.startswith("a"):
        return [i for i in new if not i.needs_agent]
    if answer.startswith("p"):
        return _pick(new, ask)
    return []


def _found(new: list[Importable]) -> str:
    counts = listing.counts(listing.Importables(new, []))
    found = " and ".join(f"{n} skill{'s' if n != 1 else ''} from {agent}" for agent, n in counts.items())
    for_agents = sum(1 for i in new if i.needs_agent)
    note = f" {for_agents} of them work best handed to a coding agent; all leaves them out." if for_agents else ""
    return f"\nFound {found} on this computer.{note}"


def _pick(new: list[Importable], ask: Callable[[str], str]) -> list[Importable]:
    for n, item in enumerate(new, 1):
        flag = " (works best handed to a coding agent)" if item.needs_agent else ""
        print(f"  {n}. {item.name} · {item.agent_name}{flag}: {item.description}")
    chosen = _numbers(ask("Numbers to import (like 1 3 5-7; empty for none): "), len(new))
    return [new[n - 1] for n in sorted(chosen)]


def _numbers(text: str, most: int) -> set[int]:
    chosen: set[int] = set()
    for first, last in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", text):
        chosen.update(range(int(first), min(int(last or first), most) + 1))
    return {n for n in chosen if 1 <= n <= most}


def _report(outcomes: list[importing.ImportOutcome]) -> None:
    for o in outcomes:
        said = f"{o.action} as {o.name}" if o.name else o.action
        print(f"  {Path(o.id).name}: {said}{f' ({o.note})' if o.note else ''}")


if __name__ == "__main__":
    main()
