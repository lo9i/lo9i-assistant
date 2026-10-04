"""The message box. Files dropped on the terminal window arrive as a paste of their paths; those are
attached instead of typed, like a pasted screenshot."""

from pathlib import Path

from textual import events
from textual.message import Message
from textual.widgets import Input

from assistant.client.files import dropped_paths


class PromptInput(Input):
    class FilesDropped(Message):
        def __init__(self, paths: list[Path]) -> None:
            super().__init__()
            self.paths = paths

    def _on_paste(self, event: events.Paste) -> None:
        """Textual also runs Input's own handler, which types the paste, unless the default is prevented."""
        paths = dropped_paths(event.text)
        if paths:
            self.post_message(self.FilesDropped(paths))
            event.prevent_default()
            event.stop()
