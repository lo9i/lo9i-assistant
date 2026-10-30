"""The key bindings' footer in the language shown. Bindings keep their descriptions in English, marked with
`translatable`, as they're made when their module is imported; the footer translates each one as it shows it, and
shows them again when the language changes (`AssistantApp.refresh_language`)."""

from textual.app import ComposeResult
from textual.widgets import Footer

# Not exported by textual.widgets, which yields it from Footer.compose.
from textual.widgets._footer import FooterKey

from assistant_terminal.i18n import t


class ShownFooter(Footer):
    def compose(self) -> ComposeResult:
        for widget in super().compose():
            if isinstance(widget, FooterKey):
                widget.description = t(widget.description) if widget.description else ""
                widget.tooltip = t(str(widget.tooltip)) if widget.tooltip else None
            yield widget
