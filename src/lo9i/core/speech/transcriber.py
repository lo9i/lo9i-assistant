from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    seconds: float


class TranscriptionError(Exception):
    pass


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, model: str, languages: list[str], beam_size: int) -> Transcript:
        """Transcribe with this faster-whisper model, detecting one of `languages`. `beam_size` is how
        many candidate sentences are kept while decoding (1: greedy)."""
        ...
