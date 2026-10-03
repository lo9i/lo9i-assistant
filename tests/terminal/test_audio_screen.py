from textual.widgets import Button, Markdown, Select, SelectionList

from assistant_terminal.tui.screens import AudioScreen
from tests.terminal.conftest import wait_for


async def test_speech_to_text_and_spoken_replies_are_saved(app, client):
    async with app.run_test(size=(110, 50)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/audio", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, AudioScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#audio-body", Markdown).source

        await wait_for(pilot, lambda: "`small`, accurate, detected as Spanish, English" in body())
        screen.query_one("#audio-model", Select).value = "tiny"
        screen.query_one("#audio-decoding", Select).value = "fast"
        screen.query_one("#audio-languages", SelectionList).deselect("en")
        screen.query_one("#save-stt", Button).press()
        await wait_for(pilot, lambda: "`tiny`, fast, detected as Spanish" in body())
        assert (client.speech.state.model, client.speech.state.decoding) == ("tiny", "fast")
        screen.query_one("#audio-languages", SelectionList).deselect("es")
        screen.query_one("#save-stt", Button).press()
        await wait_for(pilot, lambda: "at least one language" in body())
        screen.query_one("#audio-spoken", Select).value = "voice"
        screen.query_one("#audio-voice", Select).value = "af_heart"
        screen.query_one("#save-replies", Button).press()
        await wait_for(pilot, lambda: "Speak replies to voice messages" in body())
        assert (client.speech.state.spoken_replies, client.speech.state.voice) == ("voice", "af_heart")
