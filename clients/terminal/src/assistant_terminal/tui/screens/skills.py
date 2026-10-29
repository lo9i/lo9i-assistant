"""Saved skills: pick one to read its instructions, edit, update or delete it, or install plugins from
the assistant's extras. Built-in skills aren't listed. Refreshes when a skill is saved, installed or deleted."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import RepositoriesApi, SkillsApi
from assistant.core.agent import Skill, SkillError, SkillSummary
from assistant_terminal.health_text import failures_line, label
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.kept_keys import ask_about_keys
from assistant_terminal.tui.screens.skill_edit import SkillEditScreen


class SkillsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"skills"})

    def __init__(self, skills: SkillsApi, repositories: RepositoriesApi) -> None:
        super().__init__()
        self._skills = skills
        # For deleting what a removed skill left kept (its private repository's token).
        self._repositories = repositories
        self._names: list[str] = []
        self._summaries: dict[str, SkillSummary] = {}
        self._selected: str | None = None
        self._skill: Skill | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="skills"):
            yield Static("Skills", id="skills-title")
            yield Static(
                "No skills yet. Ask the assistant to save one, for example: “save a skill for my daily news digest”, "
                "or install one from the assistant's extras with /plugins.",
                id="skills-empty",
            )
            with Horizontal(id="skills-main"):
                yield OptionList(id="skills-list")
                yield Static(classes="divider")
                with VerticalScroll(id="skills-detail"):
                    yield Markdown(id="skill-body")
            with Horizontal(id="skills-buttons"):
                yield Button("Edit", id="edit")
                yield Button("Update", id="update")
                yield Button("Delete", variant="error", id="delete")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a skill is saved or deleted."""
        skills = await self._skills.list()
        self._names = [s.name for s in skills]
        self._summaries = {s.name: s for s in skills}
        options = self.query_one("#skills-list", OptionList)
        options.clear_options()
        # Only names and whether it's broken; the rest is in the detail next to the list.
        options.add_options([Option(f"{s.name}{_state(s)}", id=s.name) for s in skills])
        # Empty: just the message, and the dialog shrinks to fit.
        self.query_one("#skills").set_class(not skills, "empty")
        if not skills:
            for button in ("#delete", "#edit", "#update"):
                self.query_one(button).display = False
            self._selected = None
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._names else self._names[0]
        options.highlighted = self._names.index(keep)
        await self._show(keep)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None:
            await self._show(event.option.id)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#edit")
    @work
    @reports_daemon_unavailable
    async def _edit(self) -> None:
        if self._skill is not None and await self.app.push_screen_wait(SkillEditScreen(self._skills, self._skill)):
            self.notify(f"Saved skill {self._skill.name}.")
            await self.reload()

    @on(Button.Pressed, "#update")
    @reports_daemon_unavailable
    async def _update(self) -> None:
        if self._selected is None:
            return
        try:
            await self._skills.update_installed(self._selected)
            self.notify(f"Updated {self._selected} from the extras.")
        except SkillError as e:
            self.notify(str(e), severity="error")
        await self.reload()

    @on(Button.Pressed, "#delete")
    def _delete(self) -> None:
        if self._selected is not None:
            self._confirm_delete(self._selected)

    @work
    @reports_daemon_unavailable
    async def _confirm_delete(self, name: str) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(f"Delete the skill {name}?", "Delete")):
            return
        try:
            kept = await self._skills.delete(name)
            self.notify(f"Deleted skill {name}.")
        except SkillError as e:
            self.notify(str(e), severity="error")
            kept = None
        await self.reload()
        await ask_about_keys(self, self._repositories, kept)

    async def _show(self, name: str) -> None:
        self._selected, self._skill = name, None
        try:
            self._skill = await self._skills.get(name)
            text = _detail(self._skill, self._summaries.get(name))
        except SkillError as e:
            text = str(e)
        skill = self._skill
        # A skill that comes with an MCP server is updated with the server; what a plugin installed is
        # removed with the plugin, in /plugins.
        own = skill is not None and skill.server is None
        self.query_one("#edit").display = skill is not None
        self.query_one("#delete").display = skill is not None and not skill.plugin
        self.query_one("#update").display = own and skill is not None and skill.source is not None
        await self.query_one("#skill-body", Markdown).update(text)


def _state(summary: SkillSummary) -> str:
    origin = f" · plugin {summary.plugin}" if summary.plugin else ""
    return origin + (" · has problems" if summary.problems else label(summary.failing))


def _detail(skill: Skill, summary: SkillSummary | None) -> str:
    text = f"### {skill.name}\n\n{skill.description}{_health(skill, summary)}\n\n---\n\n{skill.instructions}"
    origin = f"the {skill.plugin} plugin" if skill.plugin else "you or the assistant, here"
    text += f"\n\n---\n\n**Added by** {origin}"
    if skill.files:
        text += "\n\n**Files:** " + ", ".join(f"`{path}`" for path in skill.files)
    if skill.plugin:
        text += f"\n\nTo delete it, remove the {skill.plugin} plugin in /plugins."
    if skill.server:
        text += f"\n\n**Comes with the {skill.server} MCP server**: updated with it."
    elif skill.source:
        text += f"\n\n**Installed from** {skill.source}"
    if skill.imported_from:
        text += f"\n\n**Imported from** {skill.imported_from}: /import-skills updates it when it changes there"
    return text


def _health(skill: Skill, summary: SkillSummary | None) -> str:
    parts = [f"**Problem:** {problem}" for problem in skill.problems]
    if summary is not None and (failures := failures_line(summary.failures, summary.failure, summary.failed_at)):
        parts.append(failures)
    return "".join(f"\n\n{part}" for part in parts)
