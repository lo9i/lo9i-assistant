"""Modal for an MCP server's form (core/mcp/elicitation.py): its fields to fill in, or a link it asks the user to
open. It names the server that asks, so its words aren't taken for the assistant's."""

from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, SelectionList, Static

from assistant_terminal.i18n import t, translatable


class FormScreen(ModalScreen[dict[str, Any]]):
    """Returns {"action": "accept", "content": {...}}, {"action": "decline"} or {"action": "cancel"}."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", translatable("Cancel"))]

    def __init__(self, request: dict[str, Any]) -> None:
        super().__init__()
        self._request = request
        self._fields: list[dict[str, Any]] = list(request.get("fields") or [])

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            server = escape(str(self._request.get("asked_by", "")))
            yield Static(f"[b]{t('{server} asks', server=server)}[/b]")
            yield Static(str(self._request.get("message", "")), id="form-message", markup=False)
            with VerticalScroll(id="form-fields"):
                if url := self._request.get("url"):
                    yield Static(t("It asks you to open this link:"), classes="hint")
                    yield Static(str(url), id="form-url", markup=False)
                for place, field in enumerate(self._fields):
                    yield from _field(place, field)
            with Horizontal(id="form-buttons"):
                accept = t("I opened it") if self._request.get("url") else t("Send")
                yield Button(accept, variant="success", id="accept")
                yield Button(t("Decline"), variant="error", id="decline")
                yield Button(t("Cancel (esc)"), id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "accept":
            self._accept()
        elif event.button.id == "decline":
            self.dismiss({"action": "decline"})
        else:
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss({"action": "cancel"})

    def _accept(self) -> None:
        values = {f["key"]: self._value(place) for place, f in enumerate(self._fields)}
        content = {key: value for key, value in values.items() if value is not None}
        missing = [f["title"] for f in self._fields if f.get("required") and f["key"] not in content]
        if missing:
            self.notify(t("Fill in: {fields}", fields=", ".join(missing)), severity="warning")
            return
        self.dismiss({"action": "accept", "content": content})

    def _value(self, place: int) -> Any:
        widget = self.query_one(f"#{_id(place)}")
        if isinstance(widget, Checkbox):
            return widget.value
        if isinstance(widget, SelectionList):
            return list(widget.selected)
        if isinstance(widget, Select):
            return None if widget.value is Select.NULL else widget.value
        return value if isinstance(widget, Input) and (value := widget.value.strip()) else None


def _field(place: int, field: dict[str, Any]) -> ComposeResult:
    title = str(field.get("title") or field["key"]) + (" *" if field.get("required") else "")
    yield Static(title, classes="form-title", markup=False)
    if description := field.get("description"):
        yield Static(str(description), classes="hint", markup=False)
    yield _input(field, _id(place))


def _input(field: dict[str, Any], id: str) -> Checkbox | SelectionList[str] | Select[str] | Input:
    default = field.get("default")
    options = [(str(o["label"]), str(o["value"])) for o in field.get("options") or []]
    match field["type"]:
        case "boolean":
            return Checkbox(str(field.get("title") or field["key"]), bool(default), id=id)
        case "choices":
            picked = set(default or [])
            return SelectionList[str](*[(label, value, value in picked) for label, value in options], id=id)
        case "choice":
            return Select[str](options, value=str(default) if default else Select.NULL, id=id)
        case "number" | "integer":
            given = "" if default is None else str(default)
            return Input(given, type=field["type"], id=id)
        case _:
            return Input("" if default is None else str(default), placeholder=field.get("format", ""), id=id)


def _id(place: int) -> str:
    """By its place: a field's key may hold any character."""
    return f"form-field-{place}"
