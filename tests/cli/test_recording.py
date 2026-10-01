"""F3 recording with a fake microphone; hidden when no microphone is usable."""

import sys
import types

import assistant.gateways.cli.tui.app as app_module
from assistant.core.agent import Session
from assistant.gateways.cli.history import History
from assistant.gateways.cli.preferences import Preferences
from assistant.gateways.cli.tui.widgets import TranscriptNote, UserMessage
from tests.cli.conftest import wait_for


class _FakeStream:
    def __init__(self, samplerate, channels, dtype, callback):
        self._callback = callback

    def start(self):
        self._callback(b"\x00\x01" * 24000, 24000, None, None)

    def stop(self):
        pass

    def close(self):
        pass


async def test_f3_records_and_sends_a_voice_message(client, monkeypatch, tmp_path):
    fake = types.SimpleNamespace(
        RawInputStream=_FakeStream, query_devices=lambda kind: {"default_samplerate": 24000, "max_input_channels": 1}
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(app_module, "_MIN_RECORDING_SECONDS", 0)
    history, preferences = History(tmp_path / "h", limit=10), Preferences(tmp_path / "p.json")
    app = app_module.AssistantApp(client, Session("owner", "cli", "t"), history, preferences)
    async with app.run_test() as pilot:
        await pilot.press("f3")
        assert app._recorder.recording
        await pilot.press("f3")
        await wait_for(pilot, lambda: app.query(TranscriptNote))
        assert client.sent[0] == ("", [("recording.wav", "audio/wav")])
        assert "voice message" in str(app.query(UserMessage).first().render())


async def test_f3_is_disabled_without_a_microphone(app):
    async with app.run_test():
        assert app.check_action("toggle_recording", ()) is False
