"""The About you step (core/memory/about_you.py), shown when the app opens while the profile has no name, and with
/about-you: the user's name, how to reply and what they mainly want help with, saved to the profile at once. Then
the extras' plugins for what they picked, each installed only when they pick it, with the usual install."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, RadioButton, RadioSet, SelectionList, Static
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from lo9i.client.daemon_client import MemoryApi
from lo9i.core.agent import AboutYou, FoundServer, FoundSkill, MemoryEditError, Suggested
from lo9i.core.memory.about_you import HelpTopic, ReplyLength
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable

_TOPICS: dict[HelpTopic, str] = {
    "email": translatable("Email"),
    "calendar": translatable("Calendar"),
    "coding": translatable("Coding"),
    "expenses": translatable("Expenses"),
    "media": translatable("Movies and YouTube"),
    "hosts": translatable("Servers and hosts"),
}
_LENGTHS: dict[ReplyLength | None, str] = {
    "short": translatable("Short and to the point"),
    "detailed": translatable("Detailed, with explanations"),
    None: translatable("No preference"),
}


class AboutYouScreen(ModalScreen[list[Suggested] | None]):
    """Returns the plugins to offer once saved (maybe none), or None when left for later."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(None)", translatable("Later"))]

    def __init__(self, memory: MemoryApi) -> None:
        super().__init__()
        self._memory = memory

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="about-you"):
            yield Markdown(
                f"## {t('About you')}\n\n"
                + t(
                    "So the assistant knows you from the first chat. Only your name is needed; the rest you can skip, "
                    "and change any of it later with /about-you or /profile."
                )
            )
            yield Static(t("What should it call you?"), classes="about-you-label")
            yield Input(id="about-you-name", max_length=200)
            yield Static(t("Language for replies"), classes="about-you-label")
            yield Input(placeholder=t("For example English or Spanish"), id="about-you-language", max_length=100)
            yield Static(t("Replies"), classes="about-you-label")
            yield RadioSet(*[RadioButton(t(label)) for label in _LENGTHS.values()], id="about-you-length")
            yield Static(t("What do you mainly want help with? (space picks)"), classes="about-you-label")
            yield SelectionList[HelpTopic](*_topics(), id="about-you-help")
            yield Input(placeholder=t("Anything else, in your words"), id="about-you-other", max_length=500)
            yield Markdown(id="about-you-message")
            with Horizontal(id="about-you-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Later"), id="later")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one("#about-you-name", Input).focus()
        self._show((await self._memory.about_you()).answers)

    def _show(self, answers: AboutYou) -> None:
        self.query_one("#about-you-name", Input).value = answers.name
        self.query_one("#about-you-language", Input).value = answers.language
        self.query_one("#about-you-other", Input).value = answers.other_help
        buttons = list(self.query_one("#about-you-length", RadioSet).query(RadioButton))
        buttons[list(_LENGTHS).index(answers.reply_length)].value = True
        topics = self.query_one("#about-you-help", SelectionList)
        for topic in answers.help_with:
            topics.select(topic)

    @on(Button.Pressed, "#later")
    def _later(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        answers = self._answers()
        if not answers.name:
            await self._say(t("Write your name."))
            return
        try:
            self.dismiss(await self._memory.save_about_you(answers))
        except MemoryEditError as e:
            await self._say(str(e))

    def _answers(self) -> AboutYou:
        picked = set(self.query_one("#about-you-help", SelectionList).selected)
        pressed = self.query_one("#about-you-length", RadioSet).pressed_index
        return AboutYou(
            self.query_one("#about-you-name", Input).value.strip(),
            self.query_one("#about-you-language", Input).value.strip(),
            list(_LENGTHS)[pressed] if pressed >= 0 else None,
            [topic for topic in _TOPICS if topic in picked],
            self.query_one("#about-you-other", Input).value.strip(),
        )

    async def _say(self, text: str) -> None:
        await self.query_one("#about-you-message", Markdown).update(f"**{text}**")


def _topics() -> list[Selection[HelpTopic]]:
    return [Selection(t(label), topic) for topic, label in _TOPICS.items()]


class SuggestedPluginsScreen(ModalScreen[FoundServer | FoundSkill | None]):
    """The extras' plugins for what the user picked; returns the one to install, or None when done."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(None)", translatable("Done"))]

    def __init__(self, suggestions: list[Suggested], installed: set[str]) -> None:
        super().__init__()
        self._plugins = {p.name: p for s in suggestions for p in [*s.servers, *s.skills]}
        self._suggestions, self._installed = suggestions, installed

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="suggested-plugins"):
            yield Markdown(
                f"## {t('Plugins for what you picked')}\n\n"
                + t("Enter installs the one picked; nothing is installed otherwise. They're in /plugins too.")
            )
            yield OptionList(*[o for s in self._suggestions for o in self._options(s)], id="suggested-plugins-list")
            with Horizontal(id="suggested-plugins-buttons"):
                yield Button(t("Done"), variant="success", id="done")

    def on_mount(self) -> None:
        self.query_one("#suggested-plugins-list").focus()

    def _options(self, suggested: Suggested) -> list[Option]:
        topic = t(_TOPICS[suggested.topic])
        return [self._option(topic, p) for p in [*suggested.servers, *suggested.skills]]

    def _option(self, topic: str, plugin: FoundServer | FoundSkill) -> Option:
        done = plugin.name in self._installed
        mark = f" ({t('installed')})" if done else ""
        return Option(f"{topic}: {plugin.name}{mark} — {plugin.description}", id=plugin.name, disabled=done)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._plugins[event.option.id or ""])

    @on(Button.Pressed, "#done")
    def _done(self) -> None:
        self.dismiss(None)
