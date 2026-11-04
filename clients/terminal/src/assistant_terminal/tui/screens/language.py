"""The language of the apps' own text, for every app (the web app's Settings → General → Language): auto, which follows
each browser's language and is English where there's no browser, English or Spanish. `/language es` sets it too."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Markdown, OptionList
from textual.widgets.option_list import Option

from assistant.client.daemon_client.language import LanguageApi
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.page import PageScreen

_INTRO = translatable(
    "The language of the apps' own text, in every app. Auto follows each browser's language, and is English where "
    "there's no browser. The assistant replies in the language you write."
)
# Each language by its own name, as a language picker shows them.
_CHOICES = (("auto", translatable("Auto")), ("en", "English"), ("es", "Español"))


class LanguageScreen(PageScreen[None]):
    PAGE = "language"
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]

    def __init__(self, language: LanguageApi, changed: Callable[[], Awaitable[None]]) -> None:
        """`changed`: shows what the app shows after it in the new language."""
        super().__init__()
        self._language = language
        self._changed = changed

    def compose_page(self) -> ComposeResult:
        with Vertical(id="language"):
            yield Markdown("## " + t("Language") + f"\n\n{t(_INTRO)}", id="language-body")
            yield OptionList(id="language-choices")
            with Horizontal(id="language-buttons"):
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._list(await self._language.get())
        self.query_one("#language-choices", OptionList).focus()

    async def _list(self, chosen: str) -> None:
        choices = self.query_one("#language-choices", OptionList)
        choices.clear_options()
        choices.add_options([Option(f"{'●' if code == chosen else '○'} {t(name)}", id=code) for code, name in _CHOICES])
        choices.highlighted = next(n for n, (code, _) in enumerate(_CHOICES) if code == chosen)

    @on(OptionList.OptionSelected, "#language-choices")
    @reports_daemon_unavailable
    async def _pick(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        chosen = await self._language.set(event.option.id)
        await self._changed()
        await self._list(chosen)
        self.notify(t("Language set to {language}.", language=chosen))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()
