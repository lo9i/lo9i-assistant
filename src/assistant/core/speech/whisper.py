"""Local transcription with faster-whisper, on the CPU inside the container.

The model is loaded on first use and kept for the life of the process. Transcriptions run one
at a time in a worker thread, since each one uses all CPU threads.
"""

import asyncio
import io
import threading
from pathlib import Path

from faster_whisper import WhisperModel, decode_audio
from tqdm import tqdm

from assistant.core.config import settings
from assistant.core.speech.transcriber import Transcript, TranscriptionError


class FasterWhisperTranscriber:
    def __init__(self) -> None:
        self._model: WhisperModel | None = None
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes) -> Transcript:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._transcribe, audio)
            except Exception as e:
                raise TranscriptionError(f"Couldn't transcribe the voice message: {e}") from e

    def _transcribe(self, audio: bytes) -> Transcript:
        model = self._load()
        samples = decode_audio(io.BytesIO(audio))
        language = _pick_language(model, samples)
        segments, info = model.transcribe(samples, language=language, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(text=text, language=language, seconds=round(info.duration, 1))

    def _load(self) -> WhisperModel:
        if self._model is None:
            # Loading the model creates a tqdm progress bar, whose default lock starts a
            # multiprocessing helper that fails inside the full-screen terminal app.
            tqdm.set_lock(threading.RLock())
            self._model = WhisperModel(
                settings.stt_model,
                device="cpu",
                compute_type="int8",
                download_root=str(Path(settings.stt_models_dir).expanduser()),
            )
        return self._model


def _pick_language(model: WhisperModel, samples) -> str:
    """The most likely language among the configured ones (default Spanish and English)."""
    allowed = settings.stt_languages
    if len(allowed) == 1:
        return allowed[0]
    _, _, probabilities = model.detect_language(samples)
    scores = {language: p for language, p in probabilities if language in allowed}
    return max(scores, key=scores.get) if scores else allowed[0]
