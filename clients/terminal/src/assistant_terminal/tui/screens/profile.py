"""The user's profile: add, edit and remove the items of each section, as in the web app's
Settings → About you. The assistant keeps it up to date too; changes reach it from the next conversation."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Select

from assistant.client.daemon_client import MemoryApi
from assistant.core.agent import MemorySnapshot
from assistant.core.memory.profile import MAX_ITEMS
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_ABOUT = "Always in the assistant's mind. Changes apply from the next conversation."
_KEYS = "Enter on an item edits it, Delete removes it. Type below and press Enter to add one."


def _label(section: str) -> str:
    return section.replace("_", " ").capitalize()


class ProfileScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close"),
        Binding("delete", "remove", "Remove item"),
    ]

    def __init__(self, memory: MemoryApi) -> None:
        super().__init__()
        self._memory = memory
        self._snapshot = MemorySnapshot()
        # The index of the item being edited in the input, or None while adding.
        self._editing: int | None = None
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="profile"):
            yield Markdown(id="profile-body")
            yield Select[str]([], prompt="Section", id="profile-section")
            yield OptionList(id="profile-items")
            yield Input(id="profile-input")
            with Horizontal(id="profile-buttons"):
                yield Button("Remove item", variant="error", id="remove")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self._snapshot = await self._memory.snapshot()
        sections = self.query_one("#profile-section", Select)
        sections.set_options((_label(s), s) for s in self._snapshot.profile_sections)
        if self._snapshot.profile_sections:
            sections.value = self._snapshot.profile_sections[0]
        await self._show()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when memory changes, from the assistant or another client."""
        self._snapshot = await self._memory.snapshot()
        await self._show()

    @property
    def _section(self) -> str | None:
        value = self.query_one("#profile-section", Select).value
        return value if isinstance(value, str) else None

    @property
    def _items(self) -> list[str]:
        return list(self._snapshot.profile.get(self._section or "", []))

    @on(Select.Changed, "#profile-section")
    async def _section_changed(self) -> None:
        self._editing, self._message = None, ""
        await self._show()

    @on(OptionList.OptionSelected, "#profile-items")
    def _edit(self, event: OptionList.OptionSelected) -> None:
        self._editing = event.option_index
        prompt = self.query_one("#profile-input", Input)
        prompt.value = self._items[event.option_index]
        prompt.placeholder = "Edit the item; an empty one is removed"
        prompt.focus()

    @on(Input.Submitted, "#profile-input")
    @reports_daemon_unavailable
    async def _submit(self, event: Input.Submitted) -> None:
        text, items = event.value.strip(), self._items
        if self._editing is not None:
            items[self._editing] = text
        elif not text:
            return
        elif len(items) >= MAX_ITEMS:
            self._message = f"This section is full ({MAX_ITEMS} items). Edit or remove one to make room."
            await self._show()
            return
        else:
            items.append(text)
        event.input.value = ""
        await self._save(items)

    @on(Button.Pressed, "#remove")
    @reports_daemon_unavailable
    async def action_remove(self) -> None:
        index = self.query_one("#profile-items", OptionList).highlighted
        if index is not None and index < len(self._items):
            await self._save([item for i, item in enumerate(self._items) if i != index])

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    async def _save(self, items: list[str]) -> None:
        if self._section is None:
            return
        self._snapshot = await self._memory.set_profile_section(self._section, items)
        self._editing, self._message = None, ""
        await self._show()

    async def _show(self) -> None:
        items = self._items
        options = self.query_one("#profile-items", OptionList)
        options.clear_options()
        options.add_options(items)
        options.display = bool(items)
        prompt = self.query_one("#profile-input", Input)
        prompt.placeholder = f"Add to {_label(self._section or 'the profile').lower()}"
        count = f"{len(items)} of {MAX_ITEMS} items." if self._section else ""
        lines = ["## Profile", _ABOUT, f"{count} {_KEYS}".strip(), self._message]
        await self.query_one("#profile-body", Markdown).update("\n\n".join(line for line in lines if line))
