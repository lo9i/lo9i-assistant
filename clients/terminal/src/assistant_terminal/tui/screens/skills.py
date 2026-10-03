"""Skills: pick one to read its instructions, or delete it. Refreshes when a skill is saved or deleted."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import SkillsApi
from assistant.core.agent import SkillError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen


class SkillsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, skills: SkillsApi) -> None:
        super().__init__()
        self._skills = skills
        self._names: list[str] = []
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="skills"):
            yield Static("Skills", id="skills-title")
            yield Static(
                "No skills yet. Ask the assistant to save one, for example: “save a skill for my daily news digest”.",
                id="skills-empty",
            )
            with Horizontal(id="skills-main"):
                yield OptionList(id="skills-list")
                yield Static(classes="divider")
                with VerticalScroll(id="skills-detail"):
                    yield Markdown(id="skill-body")
            with Horizontal(id="skills-buttons"):
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
        options = self.query_one("#skills-list", OptionList)
        options.clear_options()
        # Only names; the description and instructions are in the detail next to the list.
        options.add_options([Option(name, id=name) for name in self._names])
        # Empty: just the message, and the dialog shrinks to fit.
        self.query_one("#skills").set_class(not skills, "empty")
        self.query_one("#delete").display = bool(skills)
        if not skills:
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
            await self._skills.delete(name)
            self.notify(f"Deleted skill {name}.")
        except SkillError as e:
            self.notify(str(e), severity="error")
        await self.reload()

    async def _show(self, name: str) -> None:
        self._selected = name
        try:
            skill = await self._skills.get(name)
            text = f"### {skill.name}\n\n{skill.description}\n\n---\n\n{skill.instructions}"
        except SkillError as e:
            text = str(e)
        await self.query_one("#skill-body", Markdown).update(text)
