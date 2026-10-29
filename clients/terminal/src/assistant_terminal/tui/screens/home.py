"""Home (core/home/), as the web app's Home page: each section with what the assistant last built for it from
the plugins. Showing it asks for a refresh in the background (the daemon skips one under ten minutes old) and
tells the daemon this app shows Home, so it keeps it current until the screen closes; each section's new result
shows as it's saved (a `home` event). Refresh builds every section again now. Sections are added, edited,
moved, removed, or reset to the built-in ones."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import HomeApi
from assistant.core.agent import HomePage, HomeSection, HomeSectionsError
from assistant_terminal.home_text import describe, updated
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.home_section import HomeSectionScreen

# The plugins with tools, which a section may read.
type Plugins = Callable[[], Awaitable[list[str]]]

_EMPTY = translatable("No sections. Add one, or reset to the built-in ones.")


class HomeScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", t("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"home"})

    def __init__(self, home: HomeApi, plugins: Plugins) -> None:
        super().__init__()
        self._home = home
        self._plugins = plugins
        self._page: HomePage | None = None
        self._selected = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="home"):
            yield Static(t("Home"), id="home-title")
            with Horizontal(id="home-main"):
                yield OptionList(id="home-list")
                yield Static(classes="divider")
                with VerticalScroll(id="home-detail"):
                    yield Markdown(id="home-body")
            with Horizontal(id="home-buttons"):
                yield Button(t("Refresh"), variant="primary", id="refresh")
                yield Button(t("Add"), id="add")
                yield Button(t("Edit"), id="edit")
                yield Button(t("Up"), id="up")
                yield Button(t("Down"), id="down")
                yield Button(t("Remove"), variant="error", id="remove")
                yield Button(t("Reset"), id="reset")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._home.watch()
        await self._show(await self._home.refresh(False))

    @reports_daemon_unavailable
    async def on_unmount(self) -> None:
        await self._home.unwatch()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a section's result or the sections change."""
        await self._show(await self._home.get())

    async def _show(self, page: HomePage) -> None:
        self._page = page
        ids = [c.section.id for c in page.cards]
        if self._selected not in ids:
            self._selected = ids[0] if ids else ""
        options = self.query_one("#home-list", OptionList)
        options.clear_options()
        options.add_options([Option(c.section.title, id=c.section.id) for c in page.cards])
        if self._selected:
            options.highlighted = ids.index(self._selected)
        for button in ("#edit", "#up", "#down", "#remove"):
            self.query_one(button).display = bool(ids)
        refreshing = self.query_one("#refresh", Button)
        refreshing.disabled, refreshing.label = page.refreshing, t("Refreshing…") if page.refreshing else t("Refresh")
        await self._body()

    async def _body(self) -> None:
        page, now = self._page, datetime.now().astimezone()
        card = next((c for c in page.cards if c.section.id == self._selected), None) if page else None
        title = " · ".join(filter(None, [t("Home"), updated(page.updated_at, now) if page else ""]))
        self.query_one("#home-title", Static).update(title)
        await self.query_one("#home-body", Markdown).update(describe(card, now.date()) if card else t(_EMPTY))

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or ""
        await self._body()

    @on(Button.Pressed, "#refresh")
    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self._show(await self._home.refresh(True))

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        self._edit(None)

    @on(Button.Pressed, "#edit")
    def _edit_selected(self) -> None:
        self._edit(self._section())

    @on(Button.Pressed, "#up")
    async def _up(self) -> None:
        await self._move(-1)

    @on(Button.Pressed, "#down")
    async def _down(self) -> None:
        await self._move(1)

    @on(Button.Pressed, "#remove")
    def _remove(self) -> None:
        section = self._section()
        if section is not None:
            self._confirm(t("Remove {title} from Home?", title=section.title), t("Remove"), self._without(section))

    @on(Button.Pressed, "#reset")
    def _reset(self) -> None:
        self._confirm(t("Reset Home to the built-in sections? Yours are removed."), t("Reset"), None)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @work
    @reports_daemon_unavailable
    async def _edit(self, section: HomeSection | None) -> None:
        plugins = await self._plugins()
        await self.app.push_screen_wait(HomeSectionScreen(section, plugins, self._save_edited))

    async def _save_edited(self, section: HomeSection) -> str:
        """Saves the sections with this one edited or added; returns why they were refused, "" when saved."""
        sections = self._sections()
        wanted = [section if s.id == section.id else s for s in sections] if section.id else [*sections, section]
        try:
            page = await self._home.save_sections(wanted)
        except HomeSectionsError as e:
            return str(e)
        added = {c.section.id for c in page.cards} - {s.id for s in sections}
        self._selected = section.id or next(iter(added), self._selected)
        await self._show(page)
        return ""

    async def _move(self, by: int) -> None:
        sections = self._sections()
        at = next((i for i, s in enumerate(sections) if s.id == self._selected), -1)
        if at < 0 or not 0 <= at + by < len(sections):
            return
        sections[at], sections[at + by] = sections[at + by], sections[at]
        await self._save(sections)

    def _without(self, section: HomeSection) -> list[HomeSection]:
        return [s for s in self._sections() if s.id != section.id]

    @work
    @reports_daemon_unavailable
    async def _confirm(self, question: str, action: str, sections: list[HomeSection] | None) -> None:
        """Saves `sections` once the user agrees; None resets them to the built-in ones."""
        if not await self.app.push_screen_wait(ConfirmScreen(question, action)):
            return
        if sections is None:
            await self._show(await self._home.reset_sections())
        else:
            await self._save(sections)

    @reports_daemon_unavailable
    async def _save(self, sections: list[HomeSection]) -> None:
        try:
            await self._show(await self._home.save_sections(sections))
        except HomeSectionsError as e:
            self.notify(str(e), severity="error")

    def _sections(self) -> list[HomeSection]:
        return [c.section for c in self._page.cards] if self._page else []

    def _section(self) -> HomeSection | None:
        return next((s for s in self._sections() if s.id == self._selected), None)
