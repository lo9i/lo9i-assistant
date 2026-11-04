"""A section of Settings, shown in its tab (screens/settings.py): what was a page of its own, now a widget the settings
screen holds. A section reads the daemon when it's first shown and again on the events it names in `RELOADS_ON`
(AssistantApp.reload_screen), shown or not. Its Close button closes Settings, as Esc does, after asking each section
whether it may (`may_close`: the system prompt's texts typed and not saved)."""

from typing import ClassVar

from textual.containers import Vertical
from textual.message import Message


class SettingsSection(Vertical):
    # The daemon events that change what it shows; a section that names any has a `reload`.
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset()

    class CloseAsked(Message):
        """Settings closes, once every section says it may."""

    def close(self) -> None:
        self.post_message(self.CloseAsked())

    async def may_close(self) -> bool:
        """Called from a worker, so it may ask with a dialog."""
        return True
