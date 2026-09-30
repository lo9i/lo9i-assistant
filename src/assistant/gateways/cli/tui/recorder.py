"""Microphone recording for voice messages (F3).

Only works when the app runs on the Mac: Docker has no microphone access and no audio library.
The app checks `available()` at start and hides F3 when recording can't work.
"""

import io
import time
import wave
from typing import Any

_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit


class RecordingUnavailable(Exception):
    pass


def available() -> bool:
    try:
        return int(_import_sounddevice().query_devices(kind="input")["max_input_channels"]) > 0
    except Exception:
        return False


class Recorder:
    def __init__(self) -> None:
        self._stream: Any = None
        self._frames: list[bytes] = []
        self._rate = 0
        self._started = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        sounddevice = _import_sounddevice()
        self._frames = []
        try:
            self._rate = int(sounddevice.query_devices(kind="input")["default_samplerate"])
            self._stream = sounddevice.RawInputStream(
                samplerate=self._rate, channels=_CHANNELS, dtype="int16", callback=self._on_audio
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            raise RecordingUnavailable(f"Couldn't open the microphone: {e}") from e
        self._started = time.monotonic()

    def stop(self) -> tuple[bytes, float]:
        """Stops recording. Returns the audio as WAV and its length in seconds."""
        self._stream.stop()
        self._stream.close()
        self._stream = None
        return _to_wav(b"".join(self._frames), self._rate), time.monotonic() - self._started

    def _on_audio(self, data: Any, frames: int, time_info: Any, status: Any) -> None:
        self._frames.append(bytes(data))


def _import_sounddevice() -> Any:
    try:
        import sounddevice
    except (ImportError, OSError) as e:
        raise RecordingUnavailable("Voice recording isn't available in this session.") from e
    return sounddevice


def _to_wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(_CHANNELS)
        wav.setsampwidth(_SAMPLE_WIDTH)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
