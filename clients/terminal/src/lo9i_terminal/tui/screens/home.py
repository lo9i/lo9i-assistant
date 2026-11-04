"""Home (core/home/), as the web app's Home page: each section with what the assistant last built for it from
the plugins. Showing it asks for a refresh in the background (the daemon skips one under ten minutes old) and
tells the daemon this app shows Home, so it keeps it current until the screen closes; each section's new result
shows as it's saved (a `home` event). Refresh builds every section again now. Sections are added, edited,
moved, removed, or reset to the built-in ones. Under the Open loops card, each open loop (but bills, as the card
shows them) is listed by its text, with Done and Open its conversation; returns that conversation's thread id to
open, or None."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from lo9i.client.daemon_client import HomeApi, ProactiveApi
from lo9i.core.agent import HomePage, HomeSection, HomeSectionsError, OpenLoop, ProactivePage
from lo9i.core.home.loops import shown
from lo9i.core.home.sections import LOOPS
from lo9i_terminal.home_text import describe, updated
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.loops_text import describe_loop, loop_line
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.page import PageScreen
from lo9i_terminal.tui.screens.confirm import ConfirmScreen
from lo9i_terminal.tui.screens.home_section import HomePlugins, HomeSectionScreen

# The plugins a section may read.
type Plugins = Callable[[], Awaitable[HomePlugins]]

_EMPTY = translatable("No sections. Add one, or reset to the built-in ones.")
# A loop's entry under the Open loops card: this prefix and its id.
_LOOP = "loop:"


class HomeScreen(PageScreen[str | None]):
    PAGE = "home"
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", translatable("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"home", "proactive"})

    def __init__(self, home: HomeApi, plugins: Plugins, proactive: ProactiveApi) -> None:
        super().__init__()
        self._home = home
        self._plugins = plugins
        self._proactive = proactive
        self._page: HomePage | None = None
        self._loops: list[OpenLoop] = []
        self._selected = ""

    def compose_page(self) -> ComposeResult:
        with Vertical(id="home"):
            yield Static(t("Home"), id="home-title")
            with Horizontal(id="home-main"):
                yield OptionList(id="home-list")
                yield Static(classes="divider")
                with VerticalScroll(id="home-detail"):
                    yield Markdown(id="home-body")
            with Horizontal(id="home-buttons"):
                yield Button(t("Refresh"), variant="primary", id="refresh")
                yield Button(t("Done"), variant="success", id="done")
                yield Button(t("Open its conversation"), id="open")
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
        self._keep_loops(await self._proactive.get())
        await self._show(await self._home.refresh(False))

    @reports_daemon_unavailable
    async def on_unmount(self) -> None:
        await self._home.unwatch()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a section's result, the sections or the loops change."""
        self._keep_loops(await self._proactive.get())
        await self._show(await self._home.get())

    def _keep_loops(self, page: ProactivePage) -> None:
        self._loops = shown(page.loops)

    async def _show(self, page: HomePage) -> None:
        self._page = page
        options = self._options(page)
        ids = [o.id for o in options]
        if self._selected not in ids:
            self._selected = next((i for i in ids if i), "")
        listed = self.query_one("#home-list", OptionList)
        listed.clear_options()
        listed.add_options(options)
        if self._selected:
            listed.highlighted = ids.index(self._selected)
        refreshing = self.query_one("#refresh", Button)
        refreshing.disabled, refreshing.label = page.refreshing, t("Refreshing…") if page.refreshing else t("Refresh")
        await self._body()

    def _options(self, page: HomePage) -> list[Option]:
        """Each card, and under the Open loops card its loops."""
        options = []
        for card in page.cards:
            options.append(Option(card.section.title, id=card.section.id))
            if card.section.id == LOOPS:
                options += [Option(f"  {loop_line(o)}", id=_LOOP + o.id) for o in self._loops]
        return options

    async def _body(self) -> None:
        page, now, loop = self._page, datetime.now().astimezone(), self._loop()
        card = next((c for c in page.cards if c.section.id == self._selected), None) if page else None
        title = " · ".join(filter(None, [t("Home"), updated(page.updated_at, now) if page else ""]))
        self.query_one("#home-title", Static).update(title)
        for button in ("#edit", "#up", "#down", "#remove"):
            self.query_one(button).display = card is not None
        self.query_one("#done").display = loop is not None
        self.query_one("#open").display = loop is not None and bool(loop.thread_id)
        shown_text = describe_loop(loop) if loop else describe(card, now.date()) if card else t(_EMPTY)
        await self.query_one("#home-body", Markdown).update(shown_text)

    def _loop(self) -> OpenLoop | None:
        return next((o for o in self._loops if _LOOP + o.id == self._selected), None)

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or ""
        await self._body()

    @on(Button.Pressed, "#refresh")
    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self._show(await self._home.refresh(True))

    @on(Button.Pressed, "#done")
    @reports_daemon_unavailable
    async def _done(self) -> None:
        loop = self._loop()
        if loop is not None:
            self._keep_loops(await self._proactive.close_loop(loop.id, "done"))
            self._selected = LOOPS
            if self._page is not None:
                await self._show(self._page)

    @on(Button.Pressed, "#open")
    def _open(self) -> None:
        loop = self._loop()
        if loop is not None and loop.thread_id:
            self.dismiss(loop.thread_id)

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
    def action_close(self) -> None:
        self.dismiss(None)

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
