"""A Home section, new or edited: its title, what to show (for the assistant), and the plugins it reads (none
picked: every plugin's). A section built by code (core/home/coded.py) says so, shows what it shows, and changes only
its title. Saving goes through the Home screen, which says why the sections were refused; the section stays open
then. Returns its id once saved ("" for a new one, whose id the daemon gives), None when cancelled."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, SelectionList, Static, TextArea

from assistant.core.agent import HomeSection
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

# Saves the section; returns why it was refused, "" when saved.
type Save = Callable[[HomeSection], Awaitable[str]]

_PLUGINS_NOTE = translatable("Plugins it reads; none picked, it may read every plugin. It only uses tools that read.")
_CODED_NOTE = translatable("Built by lo9i's code, not by the model: only its title can be changed here.")


class HomeSectionScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(None)", translatable("Cancel"))]

    def __init__(self, section: HomeSection | None, plugins: list[str], save: Save) -> None:
        super().__init__()
        self._section = section
        # A plugin the section names that isn't installed stays listed, so saving doesn't drop it unseen.
        self._picked = list(section.plugins) if section else []
        self._choices = sorted({*plugins, *self._picked})
        self._installed = set(plugins)
        self._save = save

    def compose(self) -> ComposeResult:
        title = t("Edit {title}", title=self._section.title) if self._section else t("New section")
        with Vertical(id="home-section"):
            yield Static(title, id="home-section-title")
            yield Input(self._section.title if self._section else "", placeholder=t("Title"), id="home-section-name")
            if self._section and self._section.coded:
                yield Static(self._section.prompt, id="home-section-shows", markup=False)
                yield Static(t(_CODED_NOTE), id="home-section-note")
            else:
                yield from self._what_to_show()
            yield Markdown(id="home-section-message")
            with Horizontal(id="home-section-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Cancel"), id="cancel")

    def _what_to_show(self) -> ComposeResult:
        yield TextArea(self._section.prompt if self._section else "", id="home-section-prompt")
        yield Static(t(_PLUGINS_NOTE), id="home-section-note")
        yield SelectionList[str](
            *[(self._label(p), p, p in self._picked) for p in self._choices], id="home-section-plugins"
        )

    def _label(self, plugin: str) -> str:
        return plugin if plugin in self._installed else t("{plugin} (not installed)", plugin=plugin)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save_pressed(self) -> None:
        title = self.query_one("#home-section-name", Input).value.strip()
        prompt, plugins = self._shown()
        message = self.query_one("#home-section-message", Markdown)
        if not title or not prompt:
            await message.update(t("**Give it a title and say what to show.**"))
            return
        section = HomeSection(
            id=self._section.id if self._section else "",
            title=title,
            prompt=prompt,
            plugins=plugins,
            columns=self._section.columns if self._section else 0,
            coded=self._section.coded if self._section else False,
        )
        if problem := await self._save(section):
            await message.update(f"**{problem}**")
            return
        self.dismiss(section.id)

    def _shown(self) -> tuple[str, list[str]]:
        """What it shows and the plugins it reads, as typed; a section built by code's are the code's."""
        if self._section and self._section.coded:
            return self._section.prompt, []
        prompt = self.query_one("#home-section-prompt", TextArea).text.strip()
        return prompt, list(self.query_one("#home-section-plugins", SelectionList).selected)
