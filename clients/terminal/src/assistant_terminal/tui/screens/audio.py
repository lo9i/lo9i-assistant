"""Audio settings: how voice messages are transcribed (model, transcription, languages) and when replies
are spoken, in which voice. The same settings as the web UI's Settings → Audio, kept by the daemon.
Spoken replies play in the web chat and as Telegram voice notes; this app doesn't play them."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Select, SelectionList, Static

from assistant.client.daemon_client import SpeechApi
from assistant.core.agent import SpeechSettingsError, SpeechStatus, SpokenReplies
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_MODEL_NOTES = {
    "tiny": "fastest, least accurate",
    "base": "fast",
    "small": "balanced",
    "medium": "slower, more accurate",
    "large-v3-turbo": "most accurate, slowest",
}
_DECODINGS = [
    ("Accurate: weighs 5 candidate sentences", "accurate"),
    ("Fast: the likeliest word each time, about twice as fast", "fast"),
]
_SPOKEN = [
    ("Don't speak replies", "off"),
    ("Speak replies to voice messages", "voice"),
    ("Speak every reply", "always"),
]
_ABOUT_SPOKEN = "Spoken replies play in the web chat and come as Telegram voice notes; this app doesn't play them."


class AudioScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"settings"})

    def __init__(self, speech: SpeechApi) -> None:
        super().__init__()
        self._speech = speech
        self._message = ""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="audio"):
            yield Markdown(id="audio-body")
            yield Static("Speech to text", classes="audio-heading")
            yield Select[str]([], prompt="Model", allow_blank=True, id="audio-model")
            yield Select[str](_DECODINGS, allow_blank=False, value="accurate", id="audio-decoding")
            yield Static("Languages voice messages are detected as (fewer, fewer mistakes):", classes="audio-note")
            yield SelectionList[str](id="audio-languages")
            yield Button("Save speech to text", variant="success", id="save-stt")
            yield Static("Spoken replies", classes="audio-heading")
            yield Select[str](_SPOKEN, allow_blank=False, value="off", id="audio-spoken")
            yield Select[str]([], prompt="Voice", allow_blank=True, id="audio-voice")
            yield Static(_ABOUT_SPOKEN, classes="audio-note")
            yield Button("Save spoken replies", variant="success", id="save-replies")
            with Horizontal(id="audio-buttons"):
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        status = await self._speech.settings()
        self.query_one("#audio-model", Select).set_options(
            [(f"{m} ({_MODEL_NOTES.get(m, '')})", m) for m in status.models]
        )
        self.query_one("#audio-voice", Select).set_options(
            [(f"{v.name} · {v.language}", v.id) for v in status.voice_options]
        )
        languages = self.query_one("#audio-languages", SelectionList)
        languages.add_options([(o.name, o.code, o.code in status.languages) for o in status.language_options])
        self._fill(status)
        await self._show(status)

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        await self._show(await self._speech.settings())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#save-stt")
    @reports_daemon_unavailable
    async def _save_stt(self) -> None:
        model = self.query_one("#audio-model", Select).value
        decoding = self.query_one("#audio-decoding", Select).value
        languages = list(self.query_one("#audio-languages", SelectionList).selected)
        try:
            status = await self._speech.change(str(model), languages, "fast" if decoding == "fast" else "accurate")
            self._message = "Saved. Used from the next voice message."
        except SpeechSettingsError as e:
            status, self._message = await self._speech.settings(), f"**{e}**"
        await self._show(status)

    @on(Button.Pressed, "#save-replies")
    @reports_daemon_unavailable
    async def _save_replies(self) -> None:
        spoken = self.query_one("#audio-spoken", Select).value
        voice = self.query_one("#audio-voice", Select).value
        mode: SpokenReplies = "voice" if spoken == "voice" else "always" if spoken == "always" else "off"
        try:
            status = await self._speech.change_replies(mode, voice if isinstance(voice, str) else "")
            self._message = "Saved."
        except SpeechSettingsError as e:
            status, self._message = await self._speech.settings(), f"**{e}**"
        await self._show(status)

    def _fill(self, status: SpeechStatus) -> None:
        self.query_one("#audio-model", Select).value = status.model
        self.query_one("#audio-decoding", Select).value = status.decoding
        self.query_one("#audio-spoken", Select).value = status.spoken_replies
        self.query_one("#audio-voice", Select).value = status.voice

    async def _show(self, status: SpeechStatus) -> None:
        names = {o.code: o.name for o in status.language_options}
        languages = ", ".join(names.get(code, code) for code in status.languages)
        decoding = "fast" if status.decoding == "fast" else "accurate"
        spoken = dict((value, label) for label, value in _SPOKEN)[status.spoken_replies]
        lines = [
            "## Audio",
            f"Voice messages: `{status.model}`, {decoding}, detected as {languages}.",
            f"{spoken}.",
        ]
        if self._message:
            lines.append(self._message)
        await self.query_one("#audio-body", Markdown).update("\n\n".join(lines))
