"""A page of the app: the sidebar on the left (sidebar.py), the page's own content beside it, filling the screen rather
than floating over the chat as a dialog, and the keys at the bottom. Each page says which of the sidebar's it is
(`PAGE`, nav.py) and composes its content in `compose_page`; Esc goes back to the chat, unless the page binds it to
something else. Dialogs opened from a page (confirming, signing in, a plugin's settings) stay dialogs over it."""

from typing import ClassVar, Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header

from assistant_terminal.nav import NavState
from assistant_terminal.tui.footer import ShownFooter
from assistant_terminal.tui.sidebar import Sidebar


class Navigation(Protocol):
    """What a page reads from the app to show its sidebar as every other one shows."""

    @property
    def nav_state(self) -> NavState: ...

    @property
    def sidebar_collapsed(self) -> bool: ...


class PageScreen[T](Screen[T]):
    # The sidebar's key for this page; "" for a page it doesn't list (/folder).
    PAGE: ClassVar[str] = ""
    # What the page opens on is its own first field or list, not the sidebar before it (F5 goes there).
    AUTO_FOCUS = "#page-body *"

    def compose(self) -> ComposeResult:
        navigation = cast(Navigation, self.app)
        yield Header()
        with Horizontal(id="page-row"):
            yield Sidebar(self.PAGE, navigation.nav_state, navigation.sidebar_collapsed)
            with Vertical(id="page-body"):
                yield from self.compose_page()
        yield ShownFooter()

    def compose_page(self) -> ComposeResult:
        raise NotImplementedError
