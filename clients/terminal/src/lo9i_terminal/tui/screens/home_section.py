"""A Home section, new or edited: its title, what to show (for the assistant), and the plugins it reads (none
picked: every plugin's). A section built by code (core/home/coded.py) says so, shows what it shows, and changes only
its title. Saving goes through the Home screen, which says why the sections were refused; the section stays open
then. Returns its id once saved ("" for a new one, whose id the daemon gives), None when cancelled."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Markdown, SelectionList, Static, Switch, TextArea

from lo9i.core.agent import HomeSection
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable

# Saves the section; returns why it was refused, "" when saved.
type Save = Callable[[HomeSection], Awaitable[str]]


@dataclass(frozen=True)
class HomePlugins:
    # The plugins with tools, which a section may read.
    names: list[str]
    # Those that list their day for lo9i: a section of one of them shows that list without the model, unless it asks
    # for the model.
    listing: list[str]


_PLUGINS_NOTE = translatable("Plugins it reads; none picked, it may read every plugin. It only uses tools that read.")
_CODED_NOTE = translatable("Built by lo9i's code, not by the model: only its title can be changed here.")
_LISTED_NOTE = translatable(
    "Off: it shows {plugin}'s own list for the day, with no model call; the text above isn't used."
)
_MODEL_NOTE = translatable(
    "On: the model builds it from the text above, which costs a model call each time it's built."
)


class HomeSectionScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(None)", translatable("Cancel"))]

    def __init__(self, section: HomeSection | None, plugins: HomePlugins, save: Save) -> None:
        super().__init__()
        self._section = section
        # A plugin the section names that isn't installed stays listed, so saving doesn't drop it unseen.
        self._picked = list(section.plugins) if section else []
        self._choices = sorted({*plugins.names, *self._picked})
        self._installed = set(plugins.names)
        self._listing = set(plugins.listing)
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
        with Horizontal(id="home-section-model"):
            yield Switch(self._section.use_model if self._section else False, id="home-section-use-model")
            yield Label(t("Use the model"))
        yield Static(id="home-section-model-note")

    def on_mount(self) -> None:
        self._show_model()

    @on(SelectionList.SelectedChanged, "#home-section-plugins")
    @on(Switch.Changed, "#home-section-use-model")
    def _show_model(self) -> None:
        """The switch shows while the section reads one plugin that lists its day."""
        if self._section and self._section.coded:
            return
        listed = self._listed()
        self.query_one("#home-section-model").display = listed is not None
        note = self.query_one("#home-section-model-note", Static)
        note.display = listed is not None
        on = self.query_one("#home-section-use-model", Switch).value
        note.update(t(_MODEL_NOTE) if on else t(_LISTED_NOTE, plugin=listed or ""))

    def _listed(self) -> str | None:
        picked = list(self.query_one("#home-section-plugins", SelectionList).selected)
        return picked[0] if len(picked) == 1 and picked[0] in self._listing else None

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
            use_model=self._use_model(),
        )
        if problem := await self._save(section):
            await message.update(f"**{problem}**")
            return
        self.dismiss(section.id)

    def _use_model(self) -> bool:
        if self._section and self._section.coded:
            return False
        return self.query_one("#home-section-use-model", Switch).value

    def _shown(self) -> tuple[str, list[str]]:
        """What it shows and the plugins it reads, as typed; a section built by code's are the code's."""
        if self._section and self._section.coded:
            return self._section.prompt, []
        prompt = self.query_one("#home-section-prompt", TextArea).text.strip()
        return prompt, list(self.query_one("#home-section-plugins", SelectionList).selected)
