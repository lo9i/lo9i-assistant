"""Settings: the web app's tabs (nav.SETTINGS_TABS), so moving between sections stays on this page. A tab with several
sections stacks them in one scroll, each under its own heading, as the web app's cards; only the last keeps its Close,
so a tab has one. It opens with the focus on the tabs: ← and → move between them, Tab goes into the one shown.
A tab's sections are built the first time it shows (`build`), so opening Settings reads only what it shows; once built
they stay, keeping what was typed in them while another tab shows, and reload on their events
(AssistantApp.reload_screen). Esc and each section's Close close Settings, once every section built says it may
(section.py)."""

from collections.abc import Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane

from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.nav import SETTINGS, SETTINGS_TABS, SettingsTab, settings_tab
from lo9i_terminal.tui.page import PageScreen
from lo9i_terminal.tui.section import SettingsSection

# A tab's pane id: this and the tab's key, apart from the ids inside the sections (#model, #skills).
_PANE = "settings-"
# A section's id: this and its key.
_SECTION = "settings-section-"


class SettingsScreen(PageScreen[None]):
    PAGE = SETTINGS
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", translatable("Close"))]

    def __init__(
        self, build: Callable[[str], SettingsSection], shown: str, section: SettingsSection | None = None
    ) -> None:
        """`build`: a section by its key. `shown`: the key of the section whose tab it opens on, with `section` when
        the caller built it (an alert's MCP server picked)."""
        super().__init__()
        self._build = build
        self._shown = shown
        self._first = section

    def compose_page(self) -> ComposeResult:
        first = settings_tab(self._shown)
        with TabbedContent(initial=_PANE + first.key, id="settings-tabs"):
            for tab in SETTINGS_TABS:
                with TabPane(t(tab.label), id=_PANE + tab.key):
                    if tab is first:
                        yield self._content(tab, {self._shown: self._first} if self._first else {})

    def on_mount(self) -> None:
        self.call_after_refresh(self._bring_into_view, self._shown)

    @property
    def shown(self) -> str:
        """The key of the tab shown."""
        return self.query_one(TabbedContent).active.removeprefix(_PANE)

    @property
    def sections(self) -> list[SettingsSection]:
        """The sections built so far, shown or not."""
        return list(self.query(SettingsSection))

    async def show(self, key: str, section: SettingsSection | None = None) -> None:
        """The tab of the section with that key, scrolled to it; with `section`, in place of the one built before."""
        tab = settings_tab(key)
        pane = self.query_one(f"#{_PANE}{tab.key}", TabPane)
        if not pane.children:
            await pane.mount(self._content(tab, {key: section} if section else {}))
        elif section is not None:
            await self._replace(key, section)
        self.query_one(TabbedContent).active = _PANE + tab.key
        self.call_after_refresh(self._bring_into_view, key)

    def _content(self, tab: SettingsTab, given: dict[str, SettingsSection]) -> Widget:
        """The tab's sections, built but those given: one alone fills the tab, several stack in a scroll."""
        sections = [self._section(key, given.get(key)) for key in tab.sections]
        if len(sections) == 1:
            return sections[0]
        # Not focused itself, so Tab from the tabs goes into the first section as in a tab of one; focus scrolls it.
        return VerticalScroll(*sections, classes="settings-stack", can_focus=False)

    def _section(self, key: str, given: SettingsSection | None) -> SettingsSection:
        section = given or self._build(key)
        section.id = _SECTION + key
        return section

    async def _replace(self, key: str, section: SettingsSection) -> None:
        old = self.query_one(f"#{_SECTION}{key}", SettingsSection)
        parent = old.parent
        assert isinstance(parent, Widget)
        await old.remove()
        # Its place among its tab's sections, which are all built: a tab builds them together.
        place = settings_tab(key).sections.index(key)
        before = place if place < len(parent.children) else None
        await parent.mount(self._section(key, section), before=before)

    def _bring_into_view(self, key: str) -> None:
        """In a tab of several, the section scrolled to the top."""
        found = self.query(f"#{_SECTION}{key}")
        if found:
            found.first().scroll_visible(top=True, animate=False)

    @on(TabbedContent.TabActivated)
    async def _activated(self, event: TabbedContent.TabActivated) -> None:
        pane = event.pane
        if pane.id is not None and not pane.children:
            tab = next(tab for tab in SETTINGS_TABS if _PANE + tab.key == pane.id)
            await pane.mount(self._content(tab, {}))

    @on(SettingsSection.CloseAsked)
    def _close_asked(self) -> None:
        self.action_close()

    @work(exclusive=True, group="close")
    async def action_close(self) -> None:
        for section in self.sections:
            if not await section.may_close():
                return
        self.dismiss()
