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
    async def transcribe(self, audio: bytes, model: str, languages: list[str]) -> Transcript:
        """Transcribe with this faster-whisper model, detecting one of `languages`."""
        ...
