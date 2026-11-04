"""Settings: one tab per section (nav.SETTINGS_TABS), as the web app's Settings has its tabs, so moving between sections
stays on this page. It opens with the focus on the tabs: ← and → move between sections, Tab goes into the one shown.
A section is built the first time its tab shows (`build`), so opening Settings reads only what it shows; once built it
stays, keeping what was typed in it while another tab shows, and reloads on its events (AssistantApp.reload_screen).
Esc and each section's Close close Settings, once every section built says it may (section.py)."""

from collections.abc import Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import TabbedContent, TabPane

from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.nav import SETTINGS, SETTINGS_TABS
from lo9i_terminal.tui.page import PageScreen
from lo9i_terminal.tui.section import SettingsSection

# A tab's pane id: this and the section's key, apart from the ids inside the sections (#model, #skills).
_PANE = "settings-"


class SettingsScreen(PageScreen[None]):
    PAGE = SETTINGS
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", translatable("Close"))]

    def __init__(
        self, build: Callable[[str], SettingsSection], shown: str, section: SettingsSection | None = None
    ) -> None:
        """`build`: a section by its key. `shown`: the key of the tab it opens on, with `section` when the caller built
        it (an alert's MCP server picked)."""
        super().__init__()
        self._build = build
        self._shown = shown
        self._first = section

    def compose_page(self) -> ComposeResult:
        with TabbedContent(initial=_PANE + self._shown, id="settings-tabs"):
            for tab in SETTINGS_TABS:
                with TabPane(t(tab.label), id=_PANE + tab.key):
                    if tab.key == self._shown:
                        yield self._first or self._build(tab.key)

    @property
    def shown(self) -> str:
        """The key of the section shown."""
        return self.query_one(TabbedContent).active.removeprefix(_PANE)

    @property
    def sections(self) -> list[SettingsSection]:
        """The sections built so far, shown or not."""
        return list(self.query(SettingsSection))

    async def show(self, key: str, section: SettingsSection | None = None) -> None:
        """That section's tab; with `section`, in place of the one built before."""
        pane = self.query_one(f"#{_PANE}{key}", TabPane)
        if section is not None:
            await pane.remove_children()
            await pane.mount(section)
        self.query_one(TabbedContent).active = _PANE + key

    @on(TabbedContent.TabActivated)
    async def _activated(self, event: TabbedContent.TabActivated) -> None:
        pane = event.pane
        if pane.id is not None and not pane.children:
            await pane.mount(self._build(pane.id.removeprefix(_PANE)))

    @on(SettingsSection.CloseAsked)
    def _close_asked(self) -> None:
        self.action_close()

    @work(exclusive=True, group="close")
    async def action_close(self) -> None:
        for section in self.sections:
            if not await section.may_close():
                return
        self.dismiss()
