"""Claude Code's and Codex's skills on this computer, to pick the ones to copy into the assistant's: whether each was
imported or changed since, and what may stop it working here, as the web app's Skills from other agents card.
Nothing is picked at first; a changed one imported again is updated."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, SelectionList, Static
from textual.widgets.selection_list import Selection

from assistant.client.daemon_client import SkillsApi
from assistant.core.agent import Importable, ImportOutcome
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class SkillImportsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"skills"})

    def __init__(self, skills: SkillsApi) -> None:
        super().__init__()
        self._skills = skills
        self._items: dict[str, Importable] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="skill-imports"):
            yield Static("Skills from other agents", id="skill-imports-title")
            yield Static("Space picks the ones to import.", classes="hint")
            yield SelectionList[str](id="skill-imports-list")
            yield Static(id="skill-imports-detail", markup=False)
            yield Static(id="skill-imports-suggestions", classes="hint", markup=False)
            yield Checkbox("Replace a skill of yours with the same name instead of adding the agent's", id="replace")
            with Horizontal(id="skill-imports-buttons"):
                yield Button("Import", variant="success", id="import")
                yield Button("Close (esc)", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()
        self.query_one("#skill-imports-list").focus()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when skills change: an import shows as imported."""
        found = await self._skills.importable()
        self._items = {i.id: i for i in found.skills}
        options = self.query_one("#skill-imports-list", SelectionList)
        options.clear_options()
        options.add_options([Selection(_label(i), i.id, False, disabled=not _selectable(i)) for i in found.skills])
        self.query_one("#import").display = bool(found.skills)
        self.query_one("#replace").display = bool(found.skills)
        self._show(found.skills[0] if found.skills else None)
        listed = ", ".join(found.suggestions)
        suggestions = f"Not imported, a coding agent's instructions (ask the assistant to read one): {listed}"
        self.query_one("#skill-imports-suggestions", Static).update(suggestions if listed else "")

    def on_selection_list_selection_highlighted(self, event: SelectionList.SelectionHighlighted) -> None:
        self._show(self._items.get(str(event.selection.value)))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#import")
    @reports_daemon_unavailable
    async def _import(self) -> None:
        picked = [str(v) for v in self.query_one("#skill-imports-list", SelectionList).selected]
        if not picked:
            self.notify("Pick the skills to import first.", severity="warning")
            return
        outcomes = await self._skills.import_skills(picked, self.query_one("#replace", Checkbox).value)
        self.notify("\n".join(_outcome(o) for o in outcomes), timeout=10)
        await self.reload()

    def _show(self, item: Importable | None) -> None:
        self.query_one("#skill-imports-detail", Static).update(_detail(item))


def _selectable(item: Importable) -> bool:
    return item.state != "imported" and not item.problems


def _label(item: Importable) -> str:
    where = f"{item.agent_name} · {item.project.rstrip('/').rsplit('/', 1)[-1]}" if item.project else item.agent_name
    state = {"imported": f" · imported as {item.name_here}", "changed": " · changed since imported"}.get(item.state, "")
    flags = " · for a coding agent" if item.needs_agent else ""
    return f"{item.name} ({where}){state}{flags}{' · has problems' if item.problems else ''}"


def _detail(item: Importable | None) -> str:
    if item is None:
        return "Claude Code and Codex have no skills on this computer."
    lines = [item.description, item.id]
    if item.state == "new" and item.renamed:
        lines.append(f"Will be {item.renamed}.")
    if item.needs_agent:
        lines.append(f"Works best handed to a coding agent: {' '.join(item.needs_agent)}")
    lines += item.problems
    return "\n".join(lines)


def _outcome(outcome: ImportOutcome) -> str:
    name = outcome.id.rstrip("/").rsplit("/", 1)[-1]
    if outcome.action == "failed":
        return f"{name}: {outcome.note}"
    return f"{name}: {outcome.action} as {outcome.name}{f' ({outcome.note})' if outcome.note else ''}"
