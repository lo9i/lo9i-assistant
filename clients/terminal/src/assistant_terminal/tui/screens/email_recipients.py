"""Who the assistant emails without asking, from any account: one list shared by every email plugin's
accounts (the web app's Settings → General → Email). Anyone else needs the user's approval."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import EmailApi
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = translatable(
    "The assistant emails these addresses without asking, from any account. Your own accounts are always allowed; "
    "anyone else needs your approval."
)


class EmailRecipientsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]

    def __init__(self, email: EmailApi) -> None:
        super().__init__()
        self._email = email

    def compose(self) -> ComposeResult:
        with Vertical(id="email-recipients"):
            yield Markdown("## " + t("Email") + f"\n\n{t(_INTRO)}", id="email-recipients-body")
            yield Input(placeholder=t("Addresses, comma-separated"), id="email-recipients-input")
            yield Markdown(id="email-recipients-message")
            with Horizontal(id="email-recipients-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one(Input).value = ", ".join(await self._email.recipients())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        saved = await self._email.set_recipients(self.query_one(Input).value.split(","))
        self.query_one(Input).value = ", ".join(saved)
        await self.query_one("#email-recipients-message", Markdown).update(t("Saved."))

    @reports_daemon_unavailable
    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._save()
