"""An option list of a list the daemon pages (`paging.Pages`): the next page loads as its end comes in sight, scrolled
to with the keys or the mouse, or because the list is shorter than the screen."""

from collections.abc import Callable

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from assistant_terminal.paging import Pages
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

# How close to the end, in rows, the next page loads.
_NEAR_END = 10


class PagedOptionList[T](OptionList):
    def __init__(self, pages: Pages[T], option: Callable[[T], Option], *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._pages = pages
        self._option = option

    def on_mount(self) -> None:
        self.watch(self, "scroll_y", self._scrolled, init=False)

    async def reload(self) -> list[T]:
        """Its items from the start again, as many as it showed. Raises DaemonUnavailableError."""
        items = await self._pages.reload()
        self.clear_options()
        self.add_options([self._option(item) for item in items])
        self.call_after_refresh(self._scrolled)
        return items

    @reports_daemon_unavailable
    async def _scrolled(self) -> None:
        if self._pages.done or self.max_scroll_y - self.scroll_y > _NEAR_END:
            return
        added = await self._pages.more()
        if added:
            self.add_options([self._option(item) for item in added])
            self.call_after_refresh(self._scrolled)
