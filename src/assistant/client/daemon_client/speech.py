from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import SpeechSettingsError, SpeechStatus
from assistant.core.agent.speech import LanguageOption, VoiceOption

_PATH = "/settings/speech"


class SpeechApi:
    """Speech to text: the model and the languages voice messages are detected as."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def settings(self) -> SpeechStatus:
        return _status(await self._transport.request("GET", _PATH))

    async def change(self, model: str, languages: list[str]) -> SpeechStatus:
        body = {"model": model, "languages": languages}
        return _status(await self._transport.request("PUT", _PATH, json=body, errors={400: SpeechSettingsError}))


def _status(data: dict) -> SpeechStatus:
    languages = [LanguageOption(**o) for o in data.pop("language_options")]
    voices = [VoiceOption(**o) for o in data.pop("voice_options")]
    return SpeechStatus(**data, language_options=languages, voice_options=voices)
