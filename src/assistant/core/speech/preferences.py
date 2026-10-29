"""Speech settings chosen in the app (Settings → Audio), stored as one Store record. Until the user
changes them, speech to text comes from .env (STT_MODEL, STT_LANGUAGES, STT_DECODING) and replies aren't
spoken. Once the user picks the apps' language (core/language.py), speech follows it: voice messages are
heard in it first, and replies are spoken in its voice unless the user picked one."""

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core import language
from assistant.core.config import settings
from assistant.core.language import Language
from assistant.core.speech.voices import default_voice, voice

_NAMESPACE = ("settings",)
_KEY = "speech"

# faster-whisper models, smallest and fastest first. Each downloads on first use.
MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]
# Languages offered for voice messages (Whisper codes). Whisper knows more; these cover most users.
LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "nl": "Dutch",
    "ca": "Catalan",
    "pl": "Polish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "ar": "Arabic",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}


# How Whisper picks the transcript: accurate keeps 5 candidate sentences going and picks the best
# (beam search); fast takes the likeliest next word each time (greedy), about twice as fast.
Decoding = Literal["accurate", "fast"]
DECODINGS: dict[str, int] = {"accurate": 5, "fast": 1}

# When replies are also spoken: never, when the user's message was a voice message, or always.
SpokenReplies = Literal["off", "voice", "always"]
SPOKEN_REPLIES: list[SpokenReplies] = ["off", "voice", "always"]


class SpeechSettingsError(Exception):
    pass


@dataclass
class SpeechSettings:
    # The faster-whisper model that transcribes voice messages.
    model: str = field(default_factory=lambda: settings.stt_model)
    # Voice messages are detected as one of these languages.
    languages: list[str] = field(default_factory=lambda: list(settings.stt_languages))
    decoding: Decoding = field(default_factory=lambda: settings.stt_decoding)
    spoken_replies: SpokenReplies = "off"
    # A Kokoro voice id (core/speech/voices.py). Empty: the default for the first language.
    voice: str = ""

    @property
    def beam_size(self) -> int:
        return DECODINGS[self.decoding]

    @property
    def reply_voice(self) -> str:
        return self.voice or default_voice(self.languages)

    def speaks(self, after_voice_message: bool) -> bool:
        """Whether a reply is spoken, given whether the user's message was a voice message."""
        return self.spoken_replies == "always" or (self.spoken_replies == "voice" and after_voice_message)

    def following(self, chosen: Language) -> "SpeechSettings":
        """As used with the apps' language: first among the languages voice messages are told apart in (the one
        a message is taken to be in when detection can't tell, and the one the default voice speaks). Auto
        leaves them as they are."""
        if chosen == "auto":
            return self
        return replace(self, languages=[chosen, *(code for code in self.languages if code != chosen)])


async def load(store: BaseStore) -> SpeechSettings:
    """As the user saved them."""
    item = await store.aget(_NAMESPACE, _KEY)
    return SpeechSettings(**item.value) if item else SpeechSettings()


async def in_use(store: BaseStore) -> SpeechSettings:
    """As voice messages are heard and replies spoken: following the apps' language."""
    return (await load(store)).following(await language.load(store))


async def save(store: BaseStore, speech: SpeechSettings) -> None:
    """Raises SpeechSettingsError for anything that isn't one of the choices."""
    error = _problem(speech)
    if error:
        raise SpeechSettingsError(error)
    await store.aput(_NAMESPACE, _KEY, asdict(speech))


def _problem(speech: SpeechSettings) -> str:
    unknown = [code for code in speech.languages if code not in LANGUAGES]
    if speech.model not in MODELS:
        return f"Unknown model {speech.model!r}. Choose one of: {', '.join(MODELS)}."
    if not speech.languages:
        return "Choose at least one language from the list."
    if unknown:
        return f"Unknown languages: {', '.join(unknown)}."
    if speech.decoding not in DECODINGS:
        return f"Transcription must be one of: {', '.join(DECODINGS)}."
    if speech.spoken_replies not in SPOKEN_REPLIES:
        return f"Spoken replies must be one of: {', '.join(SPOKEN_REPLIES)}."
    if speech.voice and voice(speech.voice) is None:
        return f"Unknown voice {speech.voice!r}."
    return ""
