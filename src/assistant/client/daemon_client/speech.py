from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Decoding, SpeechSettingsError, SpeechStatus, SpokenReplies
from assistant.core.agent.speech import LanguageOption, VoiceOption

_PATH = "/settings/speech"


class SpeechApi:
    """Speech to text (the model, the languages voice messages are detected as, accurate or fast
    transcription) and spoken replies (when, and in which voice)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def settings(self) -> SpeechStatus:
        return _status(await self._transport.request("GET", _PATH))

    async def change(self, model: str, languages: list[str], decoding: Decoding | None = None) -> SpeechStatus:
        """Without `decoding`, it stays as it is."""
        body = {"model": model, "languages": languages, "decoding": decoding}
        return _status(await self._transport.request("PUT", _PATH, json=body, errors={400: SpeechSettingsError}))

    async def change_replies(self, spoken_replies: SpokenReplies, voice: str) -> SpeechStatus:
        """off, voice (after a voice message) or always; `voice` empty for the first language's default."""
        body = {"spoken_replies": spoken_replies, "voice": voice}
        errors = {400: SpeechSettingsError}
        return _status(await self._transport.request("PUT", f"{_PATH}/replies", json=body, errors=errors))


def _status(data: dict) -> SpeechStatus:
    languages = [LanguageOption(**o) for o in data.pop("language_options")]
    voices = [VoiceOption(**o) for o in data.pop("voice_options")]
    return SpeechStatus(**data, language_options=languages, voice_options=voices)
