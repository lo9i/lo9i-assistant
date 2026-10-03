"""Local transcription with faster-whisper, on the CPU inside the container.

The model is loaded on first use and kept until another one is asked for (Settings → Audio).
Transcriptions run one at a time in a worker thread, since each one uses all CPU threads.
"""

import asyncio
import io
import threading
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel, decode_audio
from tqdm import tqdm

from assistant.core.config import settings
from assistant.core.speech.transcriber import Transcript, TranscriptionError


class FasterWhisperTranscriber:
    def __init__(self) -> None:
        self._model: WhisperModel | None = None
        self._model_name = ""
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes, model: str, languages: list[str], beam_size: int) -> Transcript:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._transcribe, audio, model, languages, beam_size)
            except Exception as e:
                raise TranscriptionError(f"Couldn't transcribe the voice message: {e}") from e

    def _transcribe(self, audio: bytes, model_name: str, languages: list[str], beam_size: int) -> Transcript:
        model = self._load(model_name)
        samples = _mono(audio)
        language = _pick_language(model, samples, languages)
        segments, info = model.transcribe(samples, language=language, vad_filter=True, beam_size=beam_size)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(text=text, language=language, seconds=round(info.duration, 1))

    def _load(self, name: str) -> WhisperModel:
        if self._model is None or name != self._model_name:
            # Loading the model creates a tqdm progress bar, whose default lock starts a
            # multiprocessing helper that fails inside the full-screen terminal app.
            tqdm.set_lock(threading.RLock())
            self._model_name = name
            self._model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                download_root=str(Path(settings.stt_models_dir).expanduser()),
            )
        return self._model


def _mono(audio: bytes) -> np.ndarray:
    """16 kHz mono samples. decode_audio returns a (left, right) pair only when asked to split stereo."""
    samples = decode_audio(io.BytesIO(audio), split_stereo=False)
    if isinstance(samples, tuple):
        raise TranscriptionError("Expected mono audio samples.")
    return samples


def _pick_language(model: WhisperModel, samples, allowed: list[str]) -> str:
    """The most likely language among the chosen ones."""
    if len(allowed) == 1:
        return allowed[0]
    _, _, probabilities = model.detect_language(samples)
    scores = {language: p for language, p in probabilities if language in allowed}
    return max(scores, key=lambda language: scores[language]) if scores else allowed[0]
