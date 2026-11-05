"""Audio settings, as the web app's Settings → Audio cards, kept by the daemon: speech to text, how voice messages are
transcribed (model, transcription, languages), and spoken replies, when replies are spoken and in which voice. Spoken
replies play in the web chat and as Telegram voice notes; this app doesn't play them."""

from collections.abc import Awaitable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Markdown, Select, SelectionList, Static

from lo9i.client.daemon_client import SpeechApi
from lo9i.core.agent import SpeechSettingsError, SpeechStatus, SpokenReplies
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection

_MODEL_NOTES = {
    "tiny": translatable("fastest, least accurate"),
    "base": translatable("fast"),
    "small": translatable("balanced"),
    "medium": translatable("slower, more accurate"),
    "large-v3-turbo": translatable("most accurate, slowest"),
}
_DECODINGS = [
    (translatable("Accurate: weighs 5 candidate sentences"), "accurate"),
    (translatable("Fast: the likeliest word each time, about twice as fast"), "fast"),
]
_SPOKEN = [
    (translatable("Don't speak replies"), "off"),
    (translatable("Speak replies to voice messages"), "voice"),
    (translatable("Speak every reply"), "always"),
]
_ABOUT_SPOKEN = translatable(
    "Spoken replies play in the web chat and come as Telegram voice notes; this app doesn't play them. Until you "
    "pick a voice, it follows the apps' language (/language)."
)
# The languages voice messages are told apart in (core/speech/preferences.py), by their code.
_LANGUAGES = {
    "en": translatable("English"),
    "es": translatable("Spanish"),
    "pt": translatable("Portuguese"),
    "fr": translatable("French"),
    "de": translatable("German"),
    "it": translatable("Italian"),
    "nl": translatable("Dutch"),
    "ca": translatable("Catalan"),
    "pl": translatable("Polish"),
    "ru": translatable("Russian"),
    "uk": translatable("Ukrainian"),
    "tr": translatable("Turkish"),
    "ar": translatable("Arabic"),
    "hi": translatable("Hindi"),
    "ja": translatable("Japanese"),
    "ko": translatable("Korean"),
    "zh": translatable("Chinese"),
}


def _language(code: str, name: str) -> str:
    return t(_LANGUAGES[code]) if code in _LANGUAGES else name


class _AudioCard(SettingsSection):
    """One of Audio's cards: it reads the speech settings, shows what's set under its heading, and saves its part."""

    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"settings"})

    def __init__(self, speech: SpeechApi) -> None:
        super().__init__()
        self._speech = speech
        self._message = ""

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        status = await self._speech.settings()
        self._fill(status)
        await self._show(status)

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        await self._show(await self._speech.settings())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()

    async def _saved(self, change: Awaitable[SpeechStatus], done: str) -> None:
        try:
            status = await change
            self._message = done
        except SpeechSettingsError as e:
            status, self._message = await self._speech.settings(), f"**{e}**"
        await self._show(status)

    async def _show(self, status: SpeechStatus) -> None:
        lines = [*self._lines(status), self._message] if self._message else self._lines(status)
        await self.query_one(Markdown).update("\n\n".join(lines))

    def _fill(self, status: SpeechStatus) -> None:
        raise NotImplementedError

    def _lines(self, status: SpeechStatus) -> list[str]:
        raise NotImplementedError


class SpeechToTextSection(_AudioCard):
    def compose(self) -> ComposeResult:
        with Vertical(id="audio"):
            yield Markdown(id="audio-body")
            yield Select[str]([], prompt=t("Model"), allow_blank=True, id="audio-model")
            yield Select[str](
                [(t(label), value) for label, value in _DECODINGS],
                allow_blank=False,
                value="accurate",
                id="audio-decoding",
            )
            yield Static(t("Languages voice messages are detected as (fewer, fewer mistakes):"), classes="audio-note")
            yield SelectionList[str](id="audio-languages")
            with Horizontal(classes="audio-buttons"):
                yield Button(t("Save speech to text"), variant="success", id="save-stt")
                yield Button(t("Close"), id="close")

    @on(Button.Pressed, "#save-stt")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        model = self.query_one("#audio-model", Select).value
        decoding = self.query_one("#audio-decoding", Select).value
        languages = list(self.query_one("#audio-languages", SelectionList).selected)
        change = self._speech.change(str(model), languages, "fast" if decoding == "fast" else "accurate")
        await self._saved(change, t("Saved. Used from the next voice message."))

    def _fill(self, status: SpeechStatus) -> None:
        model = self.query_one("#audio-model", Select)
        model.set_options([(f"{m} ({t(_MODEL_NOTES[m]) if m in _MODEL_NOTES else ''})", m) for m in status.models])
        self.query_one("#audio-languages", SelectionList).add_options(
            [(_language(o.code, o.name), o.code, o.code in status.languages) for o in status.language_options]
        )
        model.value = status.model
        self.query_one("#audio-decoding", Select).value = status.decoding

    def _lines(self, status: SpeechStatus) -> list[str]:
        names = {o.code: _language(o.code, o.name) for o in status.language_options}
        languages = ", ".join(names.get(code, code) for code in status.languages)
        decoding = t("fast") if status.decoding == "fast" else t("accurate")
        said = t(
            "Voice messages: {model}, {decoding}, detected as {languages}.",
            model=f"`{status.model}`",
            decoding=decoding,
            languages=languages,
        )
        return ["## " + t("Speech to text"), said]


class SpokenRepliesSection(_AudioCard):
    def compose(self) -> ComposeResult:
        with Vertical(id="spoken"):
            yield Markdown(id="spoken-body")
            yield Select[str](
                [(t(label), value) for label, value in _SPOKEN], allow_blank=False, value="off", id="audio-spoken"
            )
            yield Select[str]([], prompt=t("Voice"), allow_blank=True, id="audio-voice")
            yield Static(t(_ABOUT_SPOKEN), classes="audio-note")
            with Horizontal(classes="audio-buttons"):
                yield Button(t("Save spoken replies"), variant="success", id="save-replies")
                yield Button(t("Close"), id="close")

    @on(Button.Pressed, "#save-replies")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        spoken = self.query_one("#audio-spoken", Select).value
        voice = self.query_one("#audio-voice", Select).value
        mode: SpokenReplies = "voice" if spoken == "voice" else "always" if spoken == "always" else "off"
        await self._saved(self._speech.change_replies(mode, voice if isinstance(voice, str) else ""), t("Saved."))

    def _fill(self, status: SpeechStatus) -> None:
        voice = self.query_one("#audio-voice", Select)
        voice.set_options([(f"{v.name} · {v.language}", v.id) for v in status.voice_options])
        voice.value = status.voice
        self.query_one("#audio-spoken", Select).value = status.spoken_replies

    def _lines(self, status: SpeechStatus) -> list[str]:
        spoken = t(dict((value, label) for label, value in _SPOKEN)[status.spoken_replies])
        return ["## " + t("Spoken replies"), f"{spoken}."]
