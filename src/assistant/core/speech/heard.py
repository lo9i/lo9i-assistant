"""A recording heard once: its transcript kept for the next time it's asked for, so a voice message routed first
(core/conversation/first_message.py, from the web app's Chat in a new tab) isn't transcribed again when it's sent."""

import hashlib
from collections import OrderedDict

from assistant.core.speech.transcriber import Transcriber, Transcript

# Recordings whose transcripts are kept, the latest ones: a message is routed and sent within seconds.
_KEPT = 8

_Key = tuple[str, str, tuple[str, ...], int]


class HeardOnce:
    def __init__(self, transcriber: Transcriber) -> None:
        self._transcriber = transcriber
        self._heard: OrderedDict[_Key, Transcript] = OrderedDict()

    async def transcribe(self, audio: bytes, model: str, languages: list[str], beam_size: int) -> Transcript:
        key = (hashlib.sha256(audio).hexdigest(), model, tuple(languages), beam_size)
        if (heard := self._heard.get(key)) is not None:
            self._heard.move_to_end(key)
            return heard
        heard = await self._transcriber.transcribe(audio, model, languages, beam_size)
        self._heard[key] = heard
        while len(self._heard) > _KEPT:
            self._heard.popitem(last=False)
        return heard
