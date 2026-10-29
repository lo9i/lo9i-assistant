"""Voice attachments are transcribed once and stored as text; audio goes under uploads/audio."""

import shutil
import subprocess
from typing import cast

import pytest

from assistant.core.agent import Decoding, SpeechSettingsError
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.core.events import Transcribed
from assistant.core.speech.preferences import SpeechSettings
from assistant.core.speech.transcriber import Transcript
from assistant.core.speech.voice import transcribe_voice
from tests.conftest import collect

VOICE = Attachment("voice.ogg", "audio/ogg", b"fake audio")


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], int]] = []

    async def transcribe(self, audio: bytes, model: str, languages: list[str], beam_size: int) -> Transcript:
        self.calls.append((model, languages, beam_size))
        return Transcript(text="hola, recordame el dentista", language="es", seconds=3.2)


async def test_voice_is_saved_under_audio_and_stored_as_text(isolated_settings):
    transcripts, blocks = await transcribe_voice(FakeTranscriber(), [VOICE], SpeechSettings("small", ["es"]))
    assert transcripts[0].language == "es"
    assert "hola, recordame el dentista" in blocks[0]["text"]
    assert list((isolated_settings / "uploads" / "audio").glob("*/voice.ogg"))


async def test_send_emits_what_was_heard(service, monkeypatch):
    monkeypatch.setattr(service, "_transcriber", FakeTranscriber())
    events = await collect(service.send(await service.session("u", "telegram"), "", [VOICE]))
    assert events[0] == Transcribed("hola, recordame el dentista", "es")


async def test_voice_messages_use_the_settings_chosen_in_the_app(service, script, monkeypatch):
    transcriber = FakeTranscriber()
    monkeypatch.setattr(service, "_transcriber", transcriber)
    defaults = await service.speech_settings()
    assert (defaults.model, defaults.languages) == (settings.stt_model, settings.stt_languages)  # until changed
    with pytest.raises(SpeechSettingsError, match="Unknown model"):
        await service.set_speech("huge", ["es"])
    with pytest.raises(SpeechSettingsError, match="at least one"):
        await service.set_speech("base", [])
    status = await service.set_speech("base", ["en", "en", "pt"])
    assert status.languages == ["en", "pt"] and "large-v3-turbo" in status.models
    assert status.decoding == settings.stt_decoding == "accurate"
    script.reply("ok")
    await collect(service.send(await service.session("owner", "cli"), "", [VOICE]))
    assert transcriber.calls == [("base", ["en", "pt"], 5)]


async def test_voice_messages_are_heard_in_the_apps_language_first_once_picked(service, script, monkeypatch):
    transcriber = FakeTranscriber()
    monkeypatch.setattr(service, "_transcriber", transcriber)
    await service.set_speech("base", ["en", "pt"])
    await service.set_language("es")
    script.reply("ok")
    await collect(service.send(await service.session("owner", "cli"), "", [VOICE]))
    assert transcriber.calls == [("base", ["es", "en", "pt"], 5)]
    assert (await service.speech_settings()).languages == ["en", "pt"]  # as the user saved them


async def test_fast_transcription_keeps_one_candidate(service, script, monkeypatch):
    transcriber = FakeTranscriber()
    monkeypatch.setattr(service, "_transcriber", transcriber)
    with pytest.raises(SpeechSettingsError, match="Transcription must be one of"):
        await service.set_speech("tiny", ["es"], cast(Decoding, "fastest"))
    assert (await service.set_speech("tiny", ["es"], "fast")).decoding == "fast"
    assert (await service.set_speech("base", ["es"])).decoding == "fast"  # kept when left out
    script.reply("ok")
    await collect(service.send(await service.session("owner", "cli"), "", [VOICE]))
    assert transcriber.calls == [("base", ["es"], 1)]


@pytest.mark.live
@pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS `say` to generate speech")
async def test_real_transcription_of_spanish(tmp_path):
    from assistant.core.speech.whisper import FasterWhisperTranscriber

    audio = tmp_path / "es.aiff"
    subprocess.run(
        ["say", "-v", "Paulina", "-o", str(audio), "Hola, tengo turno con el dentista el viernes."], check=True
    )
    result = await FasterWhisperTranscriber().transcribe(audio.read_bytes(), "small", ["es", "en"], 5)
    assert result.language == "es" and "dentista" in result.text.lower()
