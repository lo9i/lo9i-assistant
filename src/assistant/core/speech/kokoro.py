"""Local speech synthesis with Kokoro (ONNX, on the CPU), for spoken replies.

The model files download on first use into the models folder and the model is kept for the life of
the process. Syntheses run one at a time in a worker thread, like transcriptions.
"""

import asyncio
from pathlib import Path

import httpx
from kokoro_onnx import Kokoro

from assistant.core.config import settings
from assistant.core.speech.synthesizer import Speech, SynthesisError
from assistant.core.speech.voices import voice

_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
# The int8 model: a quarter of the size, and faster on the CPU, for a small loss in quality.
_MODEL, _VOICES = "kokoro-v1.0.int8.onnx", "voices-v1.0.bin"
_DOWNLOAD_TIMEOUT = 600


class KokoroSynthesizer:
    def __init__(self) -> None:
        self._kokoro: Kokoro | None = None
        self._lock = asyncio.Lock()

    async def synthesize(self, text: str, voice_id: str) -> Speech:
        chosen = voice(voice_id)
        if chosen is None:
            raise SynthesisError(f"Unknown voice {voice_id!r}.")
        async with self._lock:
            try:
                kokoro = await self._load()
                samples, rate = await asyncio.to_thread(kokoro.create, text, voice=chosen.id, lang=chosen.lang)
            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as e:
                raise SynthesisError(f"Couldn't speak the reply: {e}") from e
        return Speech(samples, rate)

    async def _load(self) -> Kokoro:
        if self._kokoro is None:
            folder = Path(settings.stt_models_dir).expanduser() / "kokoro"
            self._kokoro = await asyncio.to_thread(_open, folder)
        return self._kokoro


def _open(folder: Path) -> Kokoro:
    return Kokoro(str(_download(folder, _MODEL)), str(_download(folder, _VOICES)))


def _download(folder: Path, name: str) -> Path:
    """Downloads once; a partial download is never left under the final name."""
    target = folder / name
    if target.exists():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with httpx.stream("GET", f"{_RELEASE}/{name}", timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as response:
        response.raise_for_status()
        with partial.open("wb") as out:
            for chunk in response.iter_bytes():
                out.write(chunk)
    partial.rename(target)
    return target
