"""Modal for a question with options from the agent (ask_user): a selection list, one option or several."""

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, SelectionList, Static

from assistant_terminal.i18n import t


class QuestionScreen(ModalScreen[dict[str, Any]]):
    """Returns {"choices": [picked options]}, or {"choices": None} when skipped."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "skip", t("Skip"))]

    def __init__(self, request: dict[str, Any]) -> None:
        super().__init__()
        self._question = str(request.get("question", ""))
        self._options = [str(o) for o in request.get("options", [])]
        self._multiple = bool(request.get("multiple"))

    def compose(self) -> ComposeResult:
        with Vertical(id="question"):
            yield Static(self._question, id="question-text", markup=False)
            if self._multiple:
                yield Static(t("Space picks or unpicks, Enter on Done answers."), classes="hint")
                yield SelectionList[str](*[(o, o) for o in self._options], id="question-options")
            else:
                yield OptionList(*self._options, id="question-options")
            with Horizontal(id="question-buttons"):
                if self._multiple:
                    yield Button(t("Done"), variant="success", id="done")
                yield Button(t("Skip (esc)"), id="skip")

    def on_mount(self) -> None:
        self.query_one("#question-options").focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss({"choices": [self._options[event.option_index]]})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done":
            picked = self.query_one("#question-options", SelectionList).selected
            self.dismiss({"choices": [o for o in self._options if o in picked]})
        else:
            self.action_skip()

    def action_skip(self) -> None:
        self.dismiss({"choices": None})
