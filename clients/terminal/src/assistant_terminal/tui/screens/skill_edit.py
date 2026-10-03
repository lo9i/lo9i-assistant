"""Editing a saved skill: its one-line description (when the assistant picks it) and its instructions.
Returns True when it was saved."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Static, TextArea

from assistant.client.daemon_client import SkillsApi
from assistant.core.agent import Skill, SkillError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class SkillEditScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, skills: SkillsApi, skill: Skill) -> None:
        super().__init__()
        self._skills = skills
        self._skill = skill

    def compose(self) -> ComposeResult:
        with Vertical(id="skill-edit"):
            yield Static(f"Edit the skill {self._skill.name}", id="skill-edit-title")
            yield Input(self._skill.description, placeholder="When to use it, in one line", id="skill-edit-description")
            yield TextArea(self._skill.instructions, id="skill-edit-instructions")
            yield Markdown(id="skill-edit-message")
            with Horizontal(id="skill-edit-buttons"):
                yield Button("Save", variant="success", id="save")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        description = self.query_one("#skill-edit-description", Input).value
        instructions = self.query_one("#skill-edit-instructions", TextArea).text
        try:
            await self._skills.update(self._skill.name, description, instructions)
        except SkillError as e:
            await self.query_one("#skill-edit-message", Markdown).update(f"**{e}**")
            return
        self.dismiss(True)
