"""Voice attachments are transcribed once and stored as text; audio goes under uploads/audio."""

import shutil
import subprocess

import pytest

from assistant.core.attachments import Attachment
from assistant.core.events import Transcribed
from assistant.core.speech.transcriber import Transcript
from assistant.core.speech.voice import transcribe_voice
from tests.conftest import collect

VOICE = Attachment("voice.ogg", "audio/ogg", b"fake audio")


class FakeTranscriber:
    async def transcribe(self, audio: bytes) -> Transcript:
        return Transcript(text="hola, recordame el dentista", language="es", seconds=3.2)


async def test_voice_is_saved_under_audio_and_stored_as_text(isolated_settings):
    transcripts, blocks = await transcribe_voice(FakeTranscriber(), [VOICE])
    assert transcripts[0].language == "es"
    assert "hola, recordame el dentista" in blocks[0]["text"]
    assert list((isolated_settings / "uploads" / "audio").glob("*/voice.ogg"))


async def test_send_emits_what_was_heard(service, monkeypatch):
    monkeypatch.setattr(service, "_transcriber", FakeTranscriber())
    events = await collect(service.send(await service.session("u", "telegram"), "", [VOICE]))
    assert events[0] == Transcribed("hola, recordame el dentista", "es")


@pytest.mark.live
@pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS `say` to generate speech")
async def test_real_transcription_of_spanish(tmp_path):
    from assistant.core.speech.whisper import FasterWhisperTranscriber

    audio = tmp_path / "es.aiff"
    subprocess.run(
        ["say", "-v", "Paulina", "-o", str(audio), "Hola, tengo turno con el dentista el viernes."], check=True
    )
    result = await FasterWhisperTranscriber().transcribe(audio.read_bytes())
    assert result.language == "es" and "dentista" in result.text.lower()
