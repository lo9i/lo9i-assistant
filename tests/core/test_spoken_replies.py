"""Spoken replies: when they apply, what is read aloud, and the audio formats."""

import io
import wave

import av
import numpy as np
import pytest

from assistant.core.agent import SpeechSettingsError, SynthesisError
from assistant.core.speech.encode import to_ogg_opus, to_wav
from assistant.core.speech.speakable import MAX_CHARS, speakable
from assistant.core.speech.synthesizer import Speech

_TONE = Speech(np.sin(np.linspace(0, 440 * 2 * np.pi, 24000)).astype(np.float32) * 0.3, 24000)


class _Synthesizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def synthesize(self, text: str, voice_id: str) -> Speech:
        self.calls.append((text, voice_id))
        return _TONE


def test_markdown_code_and_links_are_not_read_aloud():
    text = "# Done\n\n**Saved** the [note](https://x.y). See https://a.b\n\n```py\nprint(1)\n```\n- one\n- `two`"
    assert speakable(text) == "Done\nSaved the note. See\none\ntwo"
    long = "Sentence. " * 400
    assert len(speakable(long)) <= MAX_CHARS and speakable(long).endswith(".")


async def test_when_replies_are_spoken(service):
    assert not await service.speaks_reply(after_voice_message=True)  # off until chosen
    await service.set_spoken_replies("voice", "")
    assert await service.speaks_reply(True) and not await service.speaks_reply(False)
    status = await service.set_spoken_replies("always", "em_alex")
    assert status.voice == "em_alex" and await service.speaks_reply(False)
    with pytest.raises(SpeechSettingsError, match="Unknown voice"):
        await service.set_spoken_replies("always", "robot")


async def test_speak_uses_the_reply_voice_and_encodes(service, monkeypatch):
    synthesizer = _Synthesizer()
    monkeypatch.setattr(service, "_synthesizer", synthesizer)
    await service.set_speech("small", ["es", "en"])
    wav = await service.speak("**Hola**")
    assert synthesizer.calls == [("Hola", "ef_dora")]  # the default voice for the first language
    with wave.open(io.BytesIO(wav)) as audio:
        assert audio.getframerate() == 24000
    with pytest.raises(SynthesisError, match="nothing to read"):
        await service.speak("```\ncode only\n```")


def test_telegram_gets_ogg_opus():
    ogg = to_ogg_opus(_TONE)
    with av.open(io.BytesIO(ogg)) as container:
        stream = container.streams.audio[0]
        assert stream.codec_context.name == "opus" and stream.channels == 1
    assert to_wav(_TONE)[:4] == b"RIFF"


@pytest.mark.live
async def test_kokoro_speaks_spanish_that_whisper_understands():
    from assistant.core.speech.kokoro import KokoroSynthesizer
    from assistant.core.speech.whisper import FasterWhisperTranscriber

    speech = await KokoroSynthesizer().synthesize("Tengo turno con el dentista el viernes.", "ef_dora")
    heard = await FasterWhisperTranscriber().transcribe(to_wav(speech), "small", ["es", "en"], 5)
    assert heard.language == "es" and "dentista" in heard.text.lower()
