"""Claude Code's and Codex's skills on this computer, to pick the ones to copy into the assistant's: whether each was
imported or changed since, and what may stop it working here, as the web app's Skills from other agents card, under
the skills in Settings → Skills (/import-skills). Nothing is picked at first; a changed one imported again is
updated."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, SelectionList, Static
from textual.widgets.selection_list import Selection

from lo9i.client.daemon_client import SkillsApi
from lo9i.core.agent import Importable
from lo9i_terminal.i18n import t
from lo9i_terminal.skill_imports_text import detail, label, outcome, selectable, suggestions
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection


class SkillImportsSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"skills"})

    def __init__(self, skills: SkillsApi) -> None:
        super().__init__()
        self._skills = skills
        self._items: dict[str, Importable] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="skill-imports"):
            yield Static(t("Skills from other agents"), id="skill-imports-title")
            yield Static(t("Space picks the ones to import."), classes="hint")
            yield SelectionList[str](id="skill-imports-list")
            yield Static(id="skill-imports-detail", markup=False)
            yield Static(id="skill-imports-suggestions", classes="hint", markup=False)
            yield Checkbox(t("Replace a skill of yours with the same name instead of adding the agent's"), id="replace")
            with Horizontal(id="skill-imports-buttons"):
                yield Button(t("Import"), variant="success", id="import")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when skills change: an import shows as imported."""
        found = await self._skills.importable()
        self._items = {i.id: i for i in found.skills}
        options = self.query_one("#skill-imports-list", SelectionList)
        options.clear_options()
        options.add_options([Selection(label(i), i.id, False, disabled=not selectable(i)) for i in found.skills])
        self.query_one("#import").display = bool(found.skills)
        self.query_one("#replace").display = bool(found.skills)
        self._show(found.skills[0] if found.skills else None)
        self.query_one("#skill-imports-suggestions", Static).update(suggestions(found.suggestions))

    def on_selection_list_selection_highlighted(self, event: SelectionList.SelectionHighlighted) -> None:
        self._show(self._items.get(str(event.selection.value)))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()

    @on(Button.Pressed, "#import")
    @reports_daemon_unavailable
    async def _import(self) -> None:
        picked = [str(v) for v in self.query_one("#skill-imports-list", SelectionList).selected]
        if not picked:
            self.notify(t("Pick the skills to import first."), severity="warning")
            return
        outcomes = await self._skills.import_skills(picked, self.query_one("#replace", Checkbox).value)
        self.notify("\n".join(outcome(o) for o in outcomes), timeout=10)
        await self.reload()

    def _show(self, item: Importable | None) -> None:
        self.query_one("#skill-imports-detail", Static).update(detail(item))
