"""Installing skills from a git repository: its address, a look at the skills it offers, then the
ones to install. Returns the names installed, or an empty list."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, SelectionList

from assistant.client.daemon_client import SkillsApi
from assistant.core.agent import FoundSkill, SkillError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Install skills

From a git repository's https:// address. Their scripts run on the computer running the assistant,
so install only from people you trust."""


class SkillInstallScreen(ModalScreen[list[str]]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss([])", "Close")]

    def __init__(self, skills: SkillsApi) -> None:
        super().__init__()
        self._skills = skills

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="skill-install"):
            yield Markdown(_INTRO)
            yield Input(placeholder="https://github.com/user/skills", id="skill-install-url")
            yield Markdown(id="skill-install-message")
            yield SelectionList[str](id="skill-install-found")
            with Horizontal(id="skill-install-buttons"):
                yield Button("Look at skills", variant="primary", id="browse")
                yield Button("Install", variant="success", id="install")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#skill-install-found").display = self.query_one("#install").display = False

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss([])

    @on(Input.Changed, "#skill-install-url")
    def _url_changed(self) -> None:
        self.query_one("#skill-install-found").display = self.query_one("#install").display = False

    @on(Button.Pressed, "#browse")
    @on(Input.Submitted, "#skill-install-url")
    @reports_daemon_unavailable
    async def _browse(self) -> None:
        await self._say("Downloading…")
        try:
            found = await self._skills.browse(self._url())
        except SkillError as e:
            await self._say(f"**{e}**")
            return
        await self._show(found)

    @on(Button.Pressed, "#install")
    @reports_daemon_unavailable
    async def _install(self) -> None:
        names = list(self.query_one("#skill-install-found", SelectionList).selected)
        try:
            await self._skills.install(self._url(), names)
        except SkillError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss(names)

    async def _show(self, found: list[FoundSkill]) -> None:
        options = self.query_one("#skill-install-found", SelectionList)
        options.clear_options()
        options.add_options([(_label(s), s.name, len(found) == 1) for s in found])
        options.display = self.query_one("#install").display = True
        await self._say(f"{len(found)} skills. Check the ones to install, then Install.")

    def _url(self) -> str:
        return self.query_one("#skill-install-url", Input).value.strip()

    async def _say(self, text: str) -> None:
        await self.query_one("#skill-install-message", Markdown).update(text)


def _label(skill: FoundSkill) -> str:
    files = f" ({len(skill.files)} files)" if skill.files else ""
    return f"{skill.name}{files}: {skill.description}"
