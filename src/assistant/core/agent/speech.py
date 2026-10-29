"""Speech settings from any client (Settings → Audio), and spoken replies."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from assistant.core import language
from assistant.core.agent.base import ServiceBase
from assistant.core.speech import preferences
from assistant.core.speech.encode import to_ogg_opus, to_wav
from assistant.core.speech.preferences import (
    LANGUAGES,
    MODELS,
    Decoding,
    SpeechSettings,
    SpeechSettingsError,
    SpokenReplies,
)
from assistant.core.speech.speakable import speakable
from assistant.core.speech.synthesizer import SynthesisError
from assistant.core.speech.voices import VOICES

__all__ = [
    "Decoding",
    "LanguageOption",
    "SpeechMixin",
    "SpeechSettingsError",
    "SpeechStatus",
    "SpokenReplies",
    "SynthesisError",
    "VoiceOption",
]

AudioFormat = Literal["wav", "ogg"]


@dataclass
class LanguageOption:
    code: str
    name: str


@dataclass
class VoiceOption:
    id: str
    name: str
    language: str


@dataclass
class SpeechStatus:
    """The chosen settings and what can be chosen."""

    model: str
    languages: list[str]
    # accurate (beam search) or fast (greedy).
    decoding: Decoding
    spoken_replies: SpokenReplies
    # The voice replies are spoken in: the chosen one, or the default for the apps' language once the user picked
    # one, else for the first language.
    voice: str
    models: list[str]
    language_options: list[LanguageOption]
    voice_options: list[VoiceOption]


class SpeechMixin(ServiceBase):
    async def speech_settings(self) -> SpeechStatus:
        return await self._status(await preferences.load(self._storage.store))

    async def set_speech(self, model: str, languages: list[str], decoding: Decoding | None = None) -> SpeechStatus:
        """Used from the next voice message. Without `decoding`, it stays as it is. Raises SpeechSettingsError."""
        speech = await preferences.load(self._storage.store)
        speech.model, speech.languages = model, list(dict.fromkeys(languages))
        speech.decoding = decoding or speech.decoding
        await preferences.save(self._storage.store, speech)
        return await self._status(speech)

    async def set_spoken_replies(self, mode: SpokenReplies, voice: str) -> SpeechStatus:
        """When replies are also spoken, and in which voice. Raises SpeechSettingsError."""
        speech = await preferences.load(self._storage.store)
        speech.spoken_replies, speech.voice = mode, voice
        await preferences.save(self._storage.store, speech)
        return await self._status(speech)

    async def speaks_reply(self, after_voice_message: bool) -> bool:
        """For channels: whether to also send the reply as audio."""
        return (await preferences.load(self._storage.store)).speaks(after_voice_message)

    async def speak(self, text: str, audio_format: AudioFormat = "wav", voice: str = "") -> bytes:
        """`text` (Markdown) read aloud in the reply voice, or in `voice`. Raises SynthesisError."""
        spoken = speakable(text)
        if not spoken:
            raise SynthesisError("There's nothing to read aloud.")
        speech = await self._synthesizer.synthesize(
            spoken, voice or (await preferences.in_use(self._storage.store)).reply_voice
        )
        return await asyncio.to_thread(to_wav if audio_format == "wav" else to_ogg_opus, speech)

    async def _status(self, speech: SpeechSettings) -> SpeechStatus:
        """`speech` as saved; the voice as replies are spoken, following the apps' language."""
        return _status(speech, speech.following(await language.load(self._storage.store)).reply_voice)


def _status(speech: SpeechSettings, reply_voice: str) -> SpeechStatus:
    languages = [LanguageOption(code, name) for code, name in LANGUAGES.items()]
    voices = [VoiceOption(v.id, v.name, v.language) for v in VOICES]
    return SpeechStatus(
        model=speech.model,
        languages=speech.languages,
        decoding=speech.decoding,
        spoken_replies=speech.spoken_replies,
        voice=reply_voice,
        models=list(MODELS),
        language_options=languages,
        voice_options=voices,
    )
