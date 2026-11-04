"""The navigation on the left of every page and of the chat (nav.py): the arrows or the mouse move through it and Enter
or a click opens what's picked, which the app does (`Sidebar.Picked`). F4 collapses it to its glyphs and back."""

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from assistant_terminal.nav import NavState, entries


class Sidebar(OptionList):
    class Picked(Message):
        """A page's key, or `nav.OPEN` and the thread id of an open conversation."""

        def __init__(self, target: str) -> None:
            super().__init__()
            self.target = target

    def __init__(self, page: str, state: NavState, collapsed: bool) -> None:
        """`page`: the key of the page it's on, highlighted."""
        super().__init__(id="sidebar")
        self._page = page
        self._state = state
        self.set_class(collapsed, "collapsed")

    def on_mount(self) -> None:
        self._list()

    def show(self, state: NavState, collapsed: bool) -> None:
        self._state = state
        self.set_class(collapsed, "collapsed")
        self._list()

    @property
    def collapsed(self) -> bool:
        return self.has_class("collapsed")

    def _list(self) -> None:
        """Keeps the highlight where the user moved it, else on the page it's on."""
        kept = self.highlighted_option.id if self.highlighted_option is not None else self._page
        self.clear_options()
        lines = entries(self._page, self._state, self.collapsed)
        self.add_options([Option(text, id=key) for key, text in lines])
        ids = [key for key, _ in lines]
        self.highlighted = ids.index(kept) if kept in ids else ids.index(self._page) if self._page in ids else None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Its own: the page it's on handles its list's highlights, not these."""
        event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id is not None:
            self.post_message(self.Picked(event.option.id))
