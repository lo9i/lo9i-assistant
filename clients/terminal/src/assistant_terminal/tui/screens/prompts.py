"""The system prompt texts the user edits, as in the web app's Settings → System prompt: the persona, the
operating instructions and the channel hints. Pick one, edit its text, save it or reset it to the built-in
text; an edit applies from the next message in each conversation. When an update changed the built-in text an
edit hides, it says how, with Keep my edit. What's typed and not saved is kept per text while the screen is
open, and closing with any asks first. Refreshes when the texts change elsewhere (the `prompts` event), keeping
the focus and what's being typed."""

from collections.abc import Awaitable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from assistant.client.daemon_client import PromptsApi
from assistant.core.agent import PromptEditError, PromptSection, UnknownPromptError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen


class PromptsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]
    # The daemon events that change what it shows (AssistantApp.reload_screen).
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"prompts"})

    def __init__(self, prompts: PromptsApi) -> None:
        super().__init__()
        self._prompts = prompts
        self._shown: dict[str, PromptSection] = {}
        self._selected: str | None = None
        # What was typed and not saved, by text.
        self._drafts: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="prompts"):
            yield Static("System prompt", id="prompts-title")
            with Horizontal(id="prompts-main"):
                yield OptionList(id="prompts-list")
                yield Static(classes="divider")
                with Vertical(id="prompts-detail"):
                    yield Static(id="prompt-about", markup=False)
                    yield Static(id="prompt-changes", markup=False)
                    yield TextArea(id="prompt-text")
            with Horizontal(id="prompts-buttons"):
                yield Button("Save", variant="success", id="save")
                yield Button("Keep my edit", id="keep")
                yield Button("Reset to built-in", id="reset")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()
        self.query_one("#prompts-list", OptionList).focus()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the texts change: saved here, or from another app."""
        sections = await self._prompts.list()
        self._shown = {s.name: s for s in sections}
        options = self.query_one("#prompts-list", OptionList)
        options.clear_options()
        options.add_options([Option(s.title, id=s.name) for s in sections])
        keep = self._selected if self._selected in self._shown else sections[0].name
        options.highlighted = list(self._shown).index(keep)
        self._show(keep)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None and event.option.id != self._selected:
            self._show(event.option.id)

    @on(TextArea.Changed, "#prompt-text")
    def _typed(self, event: TextArea.Changed) -> None:
        section = self._shown.get(self._selected or "")
        if section is None:
            return
        if event.text_area.text == section.text:
            self._drafts.pop(section.name, None)
        else:
            self._drafts[section.name] = event.text_area.text

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        if self._selected is not None:
            text = self.query_one("#prompt-text", TextArea).text
            saving = self._prompts.save(self._selected, text)
            await self._change(self._selected, saving, "saved. It applies from your next message in each conversation.")

    @on(Button.Pressed, "#keep")
    @reports_daemon_unavailable
    async def _keep(self) -> None:
        if self._selected is not None:
            await self._change(self._selected, self._prompts.keep(self._selected), "your edit stays as it is.")

    @on(Button.Pressed, "#reset")
    def _reset(self) -> None:
        section = self._shown.get(self._selected or "")
        if section is not None:
            self._confirm_reset(section)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self._close()

    @work
    @reports_daemon_unavailable
    async def _confirm_reset(self, section: PromptSection) -> None:
        question = f"Reset {section.title}? Your edit is deleted and the assistant uses the built-in text again."
        if await self.app.push_screen_wait(ConfirmScreen(question, "Reset")):
            await self._change(section.name, self._prompts.reset(section.name), "back to the built-in text.")

    @work
    async def _close(self) -> None:
        unsaved = ", ".join(self._shown[name].title for name in self._drafts if name in self._shown)
        question = f"Close without saving your changes to {unsaved}?"
        if not unsaved or await self.app.push_screen_wait(ConfirmScreen(question, "Close")):
            self.dismiss()

    async def _change(self, name: str, change: Awaitable[PromptSection], done: str) -> None:
        """Saves or resets a text and says so; the reason when it couldn't."""
        try:
            saved = await change
        except (PromptEditError, UnknownPromptError) as e:
            self.notify(str(e), severity="error")
            return
        self._drafts.pop(name, None)
        self.notify(f"{saved.title}: {done}")
        await self.reload()

    def _show(self, name: str) -> None:
        self._selected = name
        section = self._shown[name]
        self.query_one("#prompt-about", Static).update(_about(section))
        area = self.query_one("#prompt-text", TextArea)
        text = self._drafts.get(name, section.text)
        # Loading puts the cursor back at the start: only when the text shown changes.
        if area.text != text:
            area.load_text(text)
        self.query_one("#reset", Button).disabled = not section.edited
        changes = self.query_one("#prompt-changes", Static)
        changes.display = self.query_one("#keep").display = bool(section.built_in_changes)
        changes.update(_changes(section))


def _changes(section: PromptSection) -> str:
    if not section.built_in_changes:
        return ""
    return (
        "The built-in text changed since you edited it; your edit is still what the assistant uses. Take what you "
        f"want into it and save, keep it as it is, or reset.\n{section.built_in_changes}"
    )


def _about(section: PromptSection) -> str:
    state = "Edited." if section.edited else "The built-in text."
    if section.problem:
        state = f"{section.problem} The assistant uses the built-in text until you reset or save it."
    return f"{section.description}\n{state}"
