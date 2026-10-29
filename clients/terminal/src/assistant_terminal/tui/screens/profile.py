"""The user's profile: add, edit and remove the items of each section, as in the web app's
Settings → About you. The assistant keeps it up to date too; changes reach it from the next conversation.
After the profile sections, what the assistant saved on its own: facts and summaries of past
conversations, edited and deleted here too."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Select

from assistant.client.daemon_client import MemoryApi
from assistant.core.agent import MemoryEditError, MemorySnapshot
from assistant.core.memory.profile import MAX_ITEMS
from assistant_terminal.i18n import t, translatable
from assistant_terminal.profile_text import section_label
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_ABOUT = translatable("Always in the assistant's mind. Changes apply from the next conversation.")
_KEYS = translatable("Enter on an item edits it, Delete removes it. Type below and press Enter to add one.")
_SAVED_ABOUT = translatable("Noted by the assistant in conversations. Enter on one edits it, Delete deletes it.")
# The sections after the profile's, by their value in the section list.
_FACTS, _EPISODES = "saved:facts", "saved:episodes"
_SAVED_LABELS = {_FACTS: translatable("Saved facts"), _EPISODES: translatable("Conversation summaries")}


class _Saved:
    """Facts and conversation summaries: (id, text) of each, newest first, edited and deleted by id."""

    def __init__(self, memory: MemoryApi) -> None:
        self._memory = memory
        self.items: dict[str, list[tuple[str, str]]] = {_FACTS: [], _EPISODES: []}

    async def load(self) -> None:
        facts, episodes = await self._memory.facts(), await self._memory.episodes()
        self.items = {_FACTS: [(f.id, f.text) for f in facts], _EPISODES: [(e.id, e.summary) for e in episodes]}

    async def edit(self, section: str, index: int, text: str) -> None:
        """Raises MemoryEditError, MemoryNotFoundError when it was deleted meanwhile."""
        item_id = self.items[section][index][0]
        if section == _FACTS:
            await self._memory.edit_fact(item_id, text)
        else:
            await self._memory.edit_episode(item_id, text)

    async def delete(self, section: str, index: int) -> None:
        item_id = self.items[section][index][0]
        if section == _FACTS:
            await self._memory.delete_fact(item_id)
        else:
            await self._memory.delete_episode(item_id)


class ProfileScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", t("Close")),
        Binding("delete", "remove", t("Remove item")),
    ]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"memory"})

    def __init__(self, memory: MemoryApi) -> None:
        super().__init__()
        self._memory = memory
        self._saved = _Saved(memory)
        self._snapshot = MemorySnapshot()
        # The index of the item being edited in the input, or None while adding.
        self._editing: int | None = None
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="profile"):
            yield Markdown(id="profile-body")
            yield Select[str]([], prompt=t("Section"), id="profile-section")
            yield OptionList(id="profile-items")
            yield Input(id="profile-input")
            with Horizontal(id="profile-buttons"):
                yield Button(t("Remove item"), variant="error", id="remove")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self._snapshot = await self._memory.snapshot()
        await self._saved.load()
        sections = self.query_one("#profile-section", Select)
        profile = [(section_label(s), s) for s in self._snapshot.profile_sections]
        sections.set_options([*profile, *((t(label), key) for key, label in _SAVED_LABELS.items())])
        if self._snapshot.profile_sections:
            sections.value = self._snapshot.profile_sections[0]
        await self._show()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when memory changes, from the assistant or another client."""
        self._snapshot = await self._memory.snapshot()
        await self._saved.load()
        await self._show()

    @property
    def _section(self) -> str | None:
        value = self.query_one("#profile-section", Select).value
        return value if isinstance(value, str) else None

    @property
    def _items(self) -> list[str]:
        if self._section in _SAVED_LABELS:
            return [text for _, text in self._saved.items[self._section]]
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
        prompt.placeholder = t("Edit the item; an empty one is removed")
        prompt.focus()

    @on(Input.Submitted, "#profile-input")
    @reports_daemon_unavailable
    async def _submit(self, event: Input.Submitted) -> None:
        if self._section in _SAVED_LABELS:
            await self._submit_saved(self._section, event)
            return
        text, items = event.value.strip(), self._items
        if self._editing is not None:
            items[self._editing] = text
        elif not text:
            return
        elif len(items) >= MAX_ITEMS:
            self._message = t("This section is full ({count} items). Edit or remove one to make room.", count=MAX_ITEMS)
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
        if index is None or index >= len(self._items):
            return
        if self._section in _SAVED_LABELS:
            self._confirm_delete(self._section, index)
        else:
            await self._save([item for i, item in enumerate(self._items) if i != index])

    async def _submit_saved(self, section: str, event: Input.Submitted) -> None:
        """Nothing is added here: the assistant saves these. Empty text would leave an empty memory."""
        if self._editing is None or not event.value.strip():
            self._message = t("Pick one to edit it. Delete deletes it.")
            await self._show()
            return
        try:
            await self._saved.edit(section, self._editing, event.value.strip())
        except MemoryEditError as e:
            self._message = str(e)
        event.input.value = ""
        await self._after_saved_change()

    @work
    @reports_daemon_unavailable
    async def _confirm_delete(self, section: str, index: int) -> None:
        text = self._items[index]
        if not await self.app.push_screen_wait(ConfirmScreen(t("Delete “{text}”?", text=text), t("Delete"))):
            return
        try:
            await self._saved.delete(section, index)
        except MemoryEditError as e:
            self._message = str(e)
        await self._after_saved_change()

    async def _after_saved_change(self) -> None:
        self._editing = None
        await self._saved.load()
        await self._show()

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
        if self._section in _SAVED_LABELS:
            prompt.placeholder = t("Enter on one above edits it here")
            saved = t("{count} saved.", count=len(items))
            lines = [f"## {t(_SAVED_LABELS[self._section])}", t(_SAVED_ABOUT), saved, self._message]
        else:
            section = section_label(self._section).lower() if self._section else t("the profile")
            prompt.placeholder = t("Add to {section}", section=section)
            count = t("{count} of {max} items.", count=len(items), max=MAX_ITEMS) if self._section else ""
            lines = ["## " + t("Profile"), t(_ABOUT), f"{count} {t(_KEYS)}".strip(), self._message]
        await self.query_one("#profile-body", Markdown).update("\n\n".join(line for line in lines if line))
