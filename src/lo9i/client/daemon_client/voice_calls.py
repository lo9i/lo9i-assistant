from urllib.parse import quote

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import VoiceCallError, VoiceCallSettings, VoiceChoiceError, VoiceKeyError
from lo9i.core.voice.realtime import Answer, RealtimeError

_SETTINGS = "/settings/voice-calls"


class VoiceCallsApi:
    """Live voice calls (core/voice/): the OpenAI key they use, and starting and ending one. The web app makes the
    calls; a call's audio goes between the browser and OpenAI."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def settings(self) -> VoiceCallSettings:
        return VoiceCallSettings(**await self._transport.request("GET", _SETTINGS))

    async def set_key(self, key: str) -> VoiceCallSettings:
        """Raises VoiceKeyError when OpenAI doesn't accept it."""
        body, errors = {"key": key}, {400: VoiceKeyError}
        return VoiceCallSettings(**await self._transport.request("PUT", f"{_SETTINGS}/key", json=body, errors=errors))

    async def remove_key(self) -> VoiceCallSettings:
        return VoiceCallSettings(**await self._transport.request("DELETE", f"{_SETTINGS}/key"))

    async def set_voice(self, voice: str) -> VoiceCallSettings:
        """Used from the next call. Raises VoiceChoiceError for one that isn't among `settings().voices`."""
        body, errors = {"voice": voice}, {400: VoiceChoiceError}
        return VoiceCallSettings(**await self._transport.request("PUT", f"{_SETTINGS}/voice", json=body, errors=errors))

    async def start(self, thread_id: str, offer: str) -> Answer:
        """OpenAI's answer to the browser's SDP offer. Raises VoiceCallError (no key, the inbox, a call on there
        already) or RealtimeError (OpenAI refused)."""
        errors = {409: VoiceCallError, 502: RealtimeError}
        path = f"/conversations/{thread_id}/voice-call"
        return Answer(**await self._transport.request("POST", path, json={"sdp": offer}, errors=errors))

    async def end(self, call_id: str) -> bool:
        """False when no such call was on."""
        return (await self._transport.request("DELETE", f"/voice-calls/{quote(call_id, safe='')}"))["ended"]
