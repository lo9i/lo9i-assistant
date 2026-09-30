"""Browse skills: pick one to read its instructions, or delete it."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import SkillsApi
from assistant.core.agent import SkillError
from assistant.gateways.cli.tui.daemon_errors import reports_daemon_unavailable


class SkillsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, skills: SkillsApi) -> None:
        super().__init__()
        self._skills = skills
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
                with VerticalScroll(id="skills-detail"):
                    yield Markdown(id="skill-body")
            with Horizontal(id="skills-buttons"):
                yield Button("Delete", variant="error", id="delete")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._reload()

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        await self._show(event.option.id)

    @reports_daemon_unavailable
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()
        elif self._selected:
            await self._delete(self._selected)

    async def _reload(self) -> None:
        skills = await self._skills.list()
        options = self.query_one("#skills-list", OptionList)
        options.clear_options()
        options.add_options([Option(f"{s.name}\n  {s.description}", id=s.name) for s in skills])
        # Empty: just the message, and the dialog shrinks to fit.
        self.query_one("#skills").set_class(not skills, "empty")
        self.query_one("#delete").display = bool(skills)
        if skills:
            options.highlighted = 0
            await self._show(skills[0].name)
        else:
            self._selected = None
            # Close is the only action left, so Enter closes the dialog.
            self.query_one("#close", Button).focus()

    async def _show(self, name: str | None) -> None:
        if name is None:
            return
        self._selected = name
        try:
            skill = await self._skills.get(name)
            text = f"### {skill.name}\n\n{skill.description}\n\n---\n\n{skill.instructions}"
        except SkillError as e:
            text = str(e)
        await self.query_one("#skill-body", Markdown).update(text)

    async def _delete(self, name: str) -> None:
        try:
            await self._skills.delete(name)
            self.notify(f"Deleted skill {name}.")
        except SkillError as e:
            self.notify(str(e), severity="error")
        await self._reload()
