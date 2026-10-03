"""Encodes synthesized speech: WAV for browsers, OGG Opus for Telegram voice notes."""

import io
import wave

import av
import numpy as np

from assistant.core.speech.synthesizer import Speech

_OPUS_RATE = 48000


def to_wav(speech: Speech) -> bytes:
    pcm = (np.clip(speech.samples, -1, 1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(speech.sample_rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


def to_ogg_opus(speech: Speech) -> bytes:
    buffer = io.BytesIO()
    with av.open(buffer, "w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=_OPUS_RATE, layout="mono")
        frame = av.AudioFrame.from_ndarray(_s16(speech.samples), format="s16", layout="mono")
        frame.sample_rate = speech.sample_rate
        resampler = av.AudioResampler(format="s16", layout="mono", rate=_OPUS_RATE)
        for resampled in [*resampler.resample(frame), *resampler.resample(None)]:
            container.mux(stream.encode(resampled))
        container.mux(stream.encode(None))
    return buffer.getvalue()


def _s16(samples: np.ndarray) -> np.ndarray:
    """Packed s16 frames are shaped (channels, samples)."""
    return (np.clip(samples, -1, 1) * 32767).astype(np.int16).reshape(1, -1)
